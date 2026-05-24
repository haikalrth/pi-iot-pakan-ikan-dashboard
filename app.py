import streamlit as st
import database # INJEKSI: Impor modul backend database kita
import paho.mqtt.client as mqtt
import paho.mqtt.publish as mqtt_publish
import threading
import time
import random
from datetime import datetime, time as dt_time, timedelta
import pytz
import pandas as pd
import altair as alt
from streamlit_autorefresh import st_autorefresh

# ─────────────────────────────────────────────
# Page Configuration
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Pakan Ikan IoT Dashboard",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Jalankan inisialisasi database dan seeding akun default
# database.init_db()

# ─────────────────────────────────────────────
# State Initialization (Login & MQTT)
# ─────────────────────────────────────────────
_lock = threading.Lock()

# Sinkronisasi status login dengan URL browser agar tahan refresh
if 'role' not in st.session_state:
    st.session_state['role'] = st.query_params.get('role', None)

# ─────────────────────────────────────────────
# Sidebar: Navigasi (hanya tampil setelah memilih peran)
# ─────────────────────────────────────────────
if st.session_state['role'] is not None:
    st.sidebar.title("🧭 Navigasi")
    if st.session_state['role'] == 'admin':
        opsi_menu = ["🏠 Beranda (Monitoring)", "🎛️ Kendali Alat", "🕒 Manajemen Jadwal", "📝 Log & Histori"]
    else:
        opsi_menu = ["🏠 Beranda (Monitoring)", "📝 Log & Histori"]

    # Ambil parameter 'page' dari URL. Jika tidak ada, default ke index 0
    halaman_aktif = st.query_params.get("page", opsi_menu[0])

    # Validasi keamanan: jika pengguna mengutak-atik URL secara manual
    if halaman_aktif not in opsi_menu:
        halaman_aktif = opsi_menu[0]

    # Dapatkan index default untuk radio button
    default_idx = opsi_menu.index(halaman_aktif)

    # Render radio button di sidebar dengan index default tersebut
    menu = st.sidebar.radio(
        "Pilih Halaman",
        options=opsi_menu,
        index=default_idx
    )

    # Update URL secara real-time setiap kali pengguna memindah halaman
    st.query_params["page"] = menu

    st.sidebar.divider()
    if st.sidebar.button("🚪 Keluar (Logout)", use_container_width=True):
        st.session_state['role'] = None
        st.query_params.clear()
        st.rerun()
else:
    menu = None


# ─────────────────────────────────────────────
# MQTT Configuration & Helpers
# ─────────────────────────────────────────────
try:
    MQTT_PREFIX = st.secrets["mqtt_prefix"]
except (FileNotFoundError, KeyError):
    MQTT_PREFIX = ""

TOPICS = [
    f"{MQTT_PREFIX}PI_fishfeeder/status/pakan",
    f"{MQTT_PREFIX}PI_fishfeeder/status/servo",
    f"{MQTT_PREFIX}PI_fishfeeder/waktu",
    f"{MQTT_PREFIX}PI_fishfeeder/device",
    f"{MQTT_PREFIX}PI_fishfeeder/feed/log",
    f"{MQTT_PREFIX}PI_fishfeeder/log",
    f"{MQTT_PREFIX}PI_fishfeeder/alarm",
]

def get_live_clock() -> str:
    wib = pytz.timezone("Asia/Jakarta")
    return datetime.now(wib).strftime("%H:%M:%S")

# ─────────────────────────────────────────────
# MQTT Inisialisasi (Cache Resource)
# Data container ditempelkan langsung ke objek klien
# ─────────────────────────────────────────────
@st.cache_resource
def init_mqtt_client():
    client_id = f"st_feeder_{random.randint(10000, 99999)}"
    
    # 1. Kompatibilitas Lintas Versi (Paho-MQTT v1 & v2)
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id)
    except AttributeError:
        client = mqtt.Client(client_id) # Fallback untuk v1.x

    # 2. Inisialisasi Kontainer Data Persisten
    client.iot_data = {
        "device_status": "Offline",
        "stok_pakan": "Menunggu...",
        "status_servo": "Mati (Standby)",
        "jam_alat": "Menunggu...",
        "logs": [],
        "mqtt_connected": False,
        "last_seen": 0
    }

    # 3. Callback Koneksi (WAJIB SUBSCRIBE DI SINI)
    def on_connect(c, userdata, flags, reason_code, properties):
        if reason_code == 0:
            print("SUKSES: Terhubung ke HiveMQ Broker!")
            c.iot_data["mqtt_connected"] = True
            # Gunakan Wildcard untuk menangkap SEMUA topik dari alat
            c.subscribe("PI_fishfeeder/#") 
        else:
            print(f"GAGAL: Terhubung dengan kode {reason_code}")

    # 4. Callback Penerima Pesan
    def on_message(c, userdata, msg):
        topic = msg.topic
        try:
            payload = msg.payload.decode('utf-8')
        except:
            payload = ""

        # print(f"📥 [MQTT MASUK] Topik: {topic} | Payload: {payload}")
            
        # Smart Presence: Catat timestamp denyut terakhir
        if topic.startswith("PI_fishfeeder/"):
            c.iot_data["last_seen"] = time.time()

        # Pemetaan Metrik
        if topic == "PI_fishfeeder/status/pakan":
            status_baru = payload.lower()
            status_lama = c.iot_data.get("stok_pakan", "").lower()
            
            c.iot_data["stok_pakan"] = payload.capitalize()
            
            # INJEKSI DATABASE: Hanya simpan jika status berubah (mencegah spam dari loop alat)
            if status_baru != status_lama and status_baru in ["habis", "aman"]:
                import database
                try:
                    database.simpan_histori(status_baru)
                    print(f"💾 [DATABASE] Status '{status_baru}' tersimpan permanen ke SQLite.")
                except Exception as e:
                    print(f"🔥 [DB ERROR] Gagal menyimpan ke SQLite: {e}")
        elif topic == "PI_fishfeeder/status/servo":
            c.iot_data["status_servo"] = payload.capitalize()
        elif topic == "PI_fishfeeder/waktu":
            c.iot_data["jam_alat"] = payload
        elif topic == "PI_fishfeeder/feed/log":
            import database
            try:
                database.simpan_perintah(payload)
                print(f"💾 [DATABASE] Perintah '{payload}' berhasil direkam ke SQLite.")
            except Exception as e:
                print(f"🔥 [DB ERROR] Gagal mencatat log perintah: {e}")
        elif topic == "PI_fishfeeder/log":
            c.iot_data["logs"].append(f"[{topic.split('/')[-1].upper()}] {payload}")

    # Pasang callback
    client.on_connect = on_connect
    client.on_message = on_message

    # 5. Eksekusi Koneksi
    try:
        broker = st.secrets.get("mqtt", {}).get("broker", "broker.hivemq.com")
        port = st.secrets.get("mqtt", {}).get("port", 1883)
        client.connect(broker, port, 60)
        client.loop_start()
    except Exception as e:
        print(f"CRITICAL ERROR - MQTT gagal dijalankan: {e}")

    return client

mqtt_client = init_mqtt_client()

# Jadikan global agar SEMUA halaman (termasuk Kendali Alat) reaktif secara real-time
st_autorefresh(interval=1000, limit=None, key="global_refresh")

# Helper publish yang ringkas
def publish_mqtt(topic: str, payload: str) -> bool:
    try:
        mqtt_client.publish(topic, payload)
        return True
    except Exception:
        return False

# Helper untuk menambah log dari luar cache (tombol kendali, dll)
def _add_log(source: str, message: str):
    ts = datetime.now(pytz.timezone("Asia/Jakarta")).strftime("%H:%M:%S")
    entry = f"[{ts}] {source} -> {message}"
    mqtt_client.iot_data["logs"].insert(0, entry)
    if len(mqtt_client.iot_data["logs"]) > 80:
        mqtt_client.iot_data["logs"] = mqtt_client.iot_data["logs"][:80]


# ─────────────────────────────────────────────
# Header Global
# ─────────────────────────────────────────────
# Render judul dan sub-judul secara rata tengah (Center Aligned)
st.markdown("<h1 style='text-align: center;'>🐟 Pakan Ikan IoT Dashboard</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #888888; font-size: 14px;'>Monitoring dan kendali perangkat Fish Feeder otomatis berbasis mikrokontroler</p>", unsafe_allow_html=True)
st.write("") # Memberikan sedikit jarak spasi (padding) ke elemen di bawahnya

# Injeksi CSS Mikro untuk mengecat ulang warna tombol primer menjadi biru fungsional.
# Ini stabil dan tidak akan mematikan fitur native theme switching.
st.markdown(
    """
    <style>
        /* Targetkan tombol primer DAN tombol submit form bawaan streamlit */
        div[data-testid="stButton"] button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button {
            background-color: #0d6efd !important;
            color: white !important;
            border: none !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:hover,
        div[data-testid="stFormSubmitButton"] button:hover {
            background-color: #0b5ed7 !important;
            color: white !important;
        }
        div[data-testid="stButton"] button[kind="primary"]:focus,
        div[data-testid="stFormSubmitButton"] button:focus {
            box-shadow: 0 0 0 0.25rem rgba(13, 110, 253, 0.5) !important;
        }
        /* Sembunyikan elemen tidak penting */
        div[data-testid="InputInstructions"] { display: none !important; }
        input[type="password"]::-ms-reveal, input[type="password"]::-ms-clear { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True
)

# ─────────────────────────────────────────────
# Landing Page (Pemilihan Peran)
# ─────────────────────────────────────────────
if st.session_state['role'] is None:
    # Trik 3 kolom untuk memusatkan konten di tengah (rasio 1:1.5:1)
    _, col_center, _ = st.columns([1, 1.5, 1])

    with col_center:
        with st.container(border=True):
            st.markdown("<h2 style='text-align: center;'>Login Pengguna</h2>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Sistem Monitoring Fish Feeder IoT</p>", unsafe_allow_html=True)
            st.write("") # Spasi

            # Menggunakan input standar tanpa wrapper st.form
            pwd = st.text_input("Password", type="password", placeholder="Masukkan kata sandi admin...")
            submit_admin = st.button("MASUK", type="primary", width="stretch")

            if submit_admin:
                if pwd.strip() == "":
                    # Munculkan peringatan jika kolom kosong
                    st.warning("⚠️ Masukkan password terlebih dahulu!")
                else:
                    login_berhasil = False
                    
                    # Pemeriksaan Koneksi Database dengan try-except
                    try:
                        if database.cek_login("admin", pwd):
                            login_berhasil = True
                    except Exception as e:
                        st.error(f"⚠️ Gagal terhubung ke Database Cloud: {e}")
                    
                    # Fallback ke Secrets cadangan
                    if not login_berhasil:
                        secret_val = st.secrets.get("admin_password")
                        if secret_val and pwd == secret_val:
                            login_berhasil = True

                    # Validasi Sesi (Session State)
                    if login_berhasil:
                        st.session_state['role'] = 'admin'
                        st.query_params['role'] = 'admin'
                        st.rerun()
                    else:
                        st.error("❌ Password salah atau akun tidak ditemukan!")
            st.divider()
            # Tombol visitor diletakkan di bawah form login utama
            if st.button("Masuk sebagai Pengunjung (Visitor)", width="stretch"):
                st.session_state['role'] = 'visitor'
                st.query_params['role'] = 'visitor' # Kunci status di URL
                st.rerun()

    st.stop() # Blokir render halaman lain

# ==========================================
# WATCHDOG TIMER: DETEKSI KONEKSI ALAT
# ==========================================
# Jika tidak ada data masuk selama lebih dari 15 detik, paksa status ke Offline
if time.time() - mqtt_client.iot_data.get("last_seen", 0) > 15:
    mqtt_client.iot_data["device_status"] = "Offline"
else:
    mqtt_client.iot_data["device_status"] = "Online"

# ─────────────────────────────────────────────
# Header Status (hanya tampil setelah login/masuk)
# ─────────────────────────────────────────────
if mqtt_client.iot_data["mqtt_connected"]:
    st.success("● Terhubung ke Jaringan Cloud")
else:
    st.warning("● Menghubungkan ke Jaringan...")

# Tarik data untuk keperluan global
status_pakan_global = mqtt_client.iot_data.get("stok_pakan", "").lower()

# Banner Tunggal Global
if status_pakan_global == "habis":
    st.error("⚠️ **PERINGATAN:** Stok pakan ikan habis! Segera isi ulang tempat pakan.")


# ─────────────────────────────────────────────
# Halaman 1: Beranda (Monitoring)
# ─────────────────────────────────────────────
if menu == "🏠 Beranda (Monitoring)":



    with st.container(border=True):
        st.header("📊 Status Realtime")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            pakan = mqtt_client.iot_data["stok_pakan"]
            delta_pakan = "✅ Aman" if pakan.lower() == "aman" else (
                "⚠️ Habis" if pakan.lower() == "habis" else None
            )
            st.metric(
                label="🍚 STOK PAKAN",
                value=pakan,
                delta=delta_pakan,
                delta_color="normal" if pakan.lower() == "aman" else "inverse",
                help="Indikator ketersediaan pelet di dalam wadah berdasarkan sensor jarak/IR."
            )

        with col2:
            servo = mqtt_client.iot_data["status_servo"]
            delta_servo = "🔓 Aktif" if servo.lower() == "aktif" else (
                "🔒 Mati" if servo.lower() == "mati" else None
            )
            st.metric(
                label="⚙️ STATUS ALAT PAKAN (SERVO)",
                value=servo,
                delta=delta_servo,
                help="Menampilkan kondisi bukaan katup servo secara waktu nyata."
            )

        with col3:
            conn_label = "Terhubung" if mqtt_client.iot_data["mqtt_connected"] else "Terputus"
            st.metric(
                label="☁️ STATUS JARINGAN CLOUD",
                value=conn_label,
                delta="● Online" if mqtt_client.iot_data["mqtt_connected"] else "● Offline",
                delta_color="normal" if mqtt_client.iot_data["mqtt_connected"] else "off",
                help="Status konektivitas dari dashboard ke server cloud."
            )

        st.write("")

        col4, col5, col6 = st.columns(3)
        with col4:
            # Hitung selisih detik
            last_seen = mqtt_client.iot_data.get("last_seen", 0)
            detik_berlalu = int(time.time() - last_seen)

            # Watchdog Evaluator
            if last_seen == 0 or detik_berlalu > 15:
                mqtt_client.iot_data["device_status"] = "Offline"
            else:
                mqtt_client.iot_data["device_status"] = "Online"

            dev = mqtt_client.iot_data["device_status"]
            st.metric(
                label="💻 STATUS ALAT FEEDER",
                value=dev,
                delta="● Aktif" if dev == "Online" else "● Tidak Aktif",
                delta_color="normal" if dev == "Online" else "inverse",
                help="Indikator status mesin Fish Feeder, apakah sedang aktif atau mati."
            )

            # Keterangan Visual (Live Counter)
            if last_seen == 0:
                st.caption("⏳ Menunggu koneksi pertama...")
            elif dev == "Online":
                st.caption(f"⚡ Ping: {detik_berlalu} dtk lalu")
            else:
                st.caption(f"❌ Terputus: {detik_berlalu} dtk lalu")

        with col5:
            st.metric(
                label="🕐 JAM SAAT INI (WIB)",
                value=get_live_clock(),
                help="Waktu lokal saat ini dalam zona Waktu Indonesia Barat (WIB)."
            )

        with col6:
            from datetime import timedelta
            now = datetime.now(pytz.timezone("Asia/Jakarta"))
            
            # 1. Ambil data jadwal dari memori atau SEDOT DARI DATABASE jika kosong
            import database
            if "jadwal_aktif" not in mqtt_client.iot_data:
                mqtt_client.iot_data["jadwal_aktif"] = database.ambil_jadwal()
                
            jadwal_aktif = mqtt_client.iot_data.get("jadwal_aktif", [])
            jadwal_str = "Menunggu Data..."
            
            if jadwal_aktif:
                # 2. Urutkan jadwal dari pagi ke malam
                jadwal_sorted = sorted(jadwal_aktif)
                next_sched_dt = None
                
                # 3. Cari jadwal terdekat di hari ini yang belum terlewat
                for j_str in jadwal_sorted:
                    try:
                        jam, mnt = map(int, j_str.split(":"))
                        kandidat_dt = now.replace(hour=jam, minute=mnt, second=0, microsecond=0)
                        if kandidat_dt > now:
                            next_sched_dt = kandidat_dt
                            break
                    except:
                        continue
                
                # 4. Jika semua jadwal hari ini sudah lewat, targetkan jadwal pertama untuk besok hari
                if next_sched_dt is None:
                    try:
                        jam, mnt = map(int, jadwal_sorted[0].split(":"))
                        next_sched_dt = now.replace(hour=jam, minute=mnt, second=0, microsecond=0) + timedelta(days=1)
                    except:
                        pass
                
                # 5. Format hasil akhir menjadi Tanggal, Bulan (Indo), Tahun dan Jam
                if next_sched_dt:
                    bulan_indo = {
                        1:"Januari", 2:"Februari", 3:"Maret", 4:"April", 
                        5:"Mei", 6:"Juni", 7:"Juli", 8:"Agustus", 
                        9:"September", 10:"Oktober", 11:"November", 12:"Desember"
                    }
                    tgl = next_sched_dt.day
                    bln = bulan_indo[next_sched_dt.month]
                    thn = next_sched_dt.year
                    waktu = next_sched_dt.strftime("%H:%M")
                    
                    jadwal_str = f"{tgl} {bln} {thn}, {waktu} WIB"
            else:
                jadwal_str = "Belum Diatur"

            st.metric(
                label="📅 JADWAL PAKAN SELANJUTNYA",
                value=jadwal_str,
                help="Jadwal otomatis terdekat alat akan membuka servo untuk memberi makan."
            )

# ─────────────────────────────────────────────
# Halaman 2: Kendali Alat
# ─────────────────────────────────────────────
elif menu == "🎛️ Kendali Alat":
    st.header("🎮 Kendali Alat (Remote Control)")

    if st.session_state['role'] != 'admin':
        st.error("🚫 **Akses Ditolak**: Fitur kendali alat ini hanya dapat diakses oleh Admin. Silakan keluar dan masuk kembali sebagai Admin.", icon="🛑")
    else:
        is_offline = mqtt_client.iot_data.get("device_status", "Offline") == "Offline"
        status_pakan = mqtt_client.iot_data.get("stok_pakan", "").lower()

        if mqtt_client.iot_data.get("device_status", "Offline") == "Offline":
            st.error("🚨 **PERINGATAN:** Perangkat ESP8266 saat ini sedang OFFLINE. Fitur kendali jarak jauh tidak akan merespons.")

        if "notif_msg" not in st.session_state:
            st.session_state.notif_msg = None
            st.session_state.notif_type = None
            st.session_state.notif_time = 0

        with st.container(border=True):
            st.info("Anda login sebagai Admin. Tekan tombol di bawah untuk mengendalikan perangkat IoT secara manual.", icon="ℹ️")
            
            # 1. Deklarasi kontainer penampung statis di atas tombol
            notif_container = st.container()

            btn1, btn2 = st.columns(2)
            with btn1:
                # HAPUS on_click. Simpan klik ke dalam variabel.
                klik_pakan = st.button("🍽️ Beri Pakan Sekarang", use_container_width=True, help="Menekan tombol ini akan memerintahkan servo untuk terbuka dan memberi makan ikan sekarang juga.")
            with btn2:
                klik_restart = st.button("🔄 Mulai Ulang Perangkat", use_container_width=True, help="Menekan tombol ini akan me-reboot atau menyalakan ulang mikrokontroler ESP8266.")

            # 2. Logika Prosedural Instan (Non-Blocking)
            import time
            is_offline = mqtt_client.iot_data.get("device_status", "Offline") == "Offline"
            status_pakan = mqtt_client.iot_data.get("stok_pakan", "").lower()

            if klik_pakan:
                if is_offline:
                    st.session_state.notif_msg = "🚨 Aksi ditolak: Perangkat sedang offline!"
                    st.session_state.notif_type = "error"
                    st.session_state.notif_time = time.time()
                elif status_pakan == "habis":
                    st.session_state.notif_msg = "Aksi ditolak: Stok pakan kosong! Isi ulang terlebih dahulu."
                    st.session_state.notif_type = "error"
                    st.session_state.notif_time = time.time()
                else:
                    # GUNAKAN HELPER BAWAAN: Eksekusi instan tanpa membuka koneksi baru
                    if publish_mqtt(topic="PI_fishfeeder/control/feed", payload="1"):
                        _add_log("KONTROL", "Beri Pakan -> PI_fishfeeder/control/feed")
                        st.session_state.notif_msg = "Perintah Beri Pakan berhasil dieksekusi!"
                        st.session_state.notif_type = "success"
                        st.session_state.notif_time = time.time()
                    else:
                        st.session_state.notif_msg = "❌ Gagal mengirim perintah ke broker MQTT."
                        st.session_state.notif_type = "error"
                        st.session_state.notif_time = time.time()
            
            elif klik_restart:
                if is_offline:
                    st.session_state.notif_msg = "🚨 Aksi ditolak: Perangkat sedang offline!"
                    st.session_state.notif_type = "error"
                    st.session_state.notif_time = time.time()
                else:
                    if publish_mqtt(topic="PI_fishfeeder/control/restart", payload="1"):
                        _add_log("KONTROL", "Mulai Ulang -> PI_fishfeeder/control/restart")
                        st.session_state.notif_msg = "Perintah Mulai Ulang berhasil dieksekusi!"
                        st.session_state.notif_type = "success"
                        st.session_state.notif_time = time.time()
                    else:
                        st.session_state.notif_msg = "❌ Gagal mengirim perintah ke broker MQTT."
                        st.session_state.notif_type = "error"
                        st.session_state.notif_time = time.time()

            # 3. RENDER NOTIFIKASI OUT-OF-ORDER (DI DALAM KONTAINER ATAS)
            with notif_container:
                if st.session_state.get("notif_msg"):
                    if (time.time() - st.session_state.get("notif_time", 0) < 4):
                        if st.session_state.notif_type == "success":
                            st.success(st.session_state.notif_msg)
                        else:
                            st.error(st.session_state.notif_msg)
                    else:
                        st.session_state.notif_msg = None
                        st.session_state.notif_type = None
                        # Tidak perlu st.empty() lagi, biarkan state None yang mematikan render


# ─────────────────────────────────────────────
# Halaman 3: Manajemen Jadwal
# ─────────────────────────────────────────────
elif menu == "🕒 Manajemen Jadwal":
    st.header("🕒 Manajemen Jadwal")

    if st.session_state['role'] != 'admin':
        st.error("🚫 **Akses Ditolak**: Fitur manajemen jadwal ini hanya dapat diakses oleh Admin. Silakan keluar dan masuk kembali sebagai Admin.", icon="🛑")
    else:
        # 1. Kontainer Notifikasi Zero-Delay (Wajib di Atas)
        notif_jadwal = st.container()

        # 2. Inisialisasi memori jadwal (Memory Persistence Anti-Refresh)
        import database
        if "jadwal_aktif" not in mqtt_client.iot_data:
            # Tarik dari SQLite, bukan hardcode RAM
            mqtt_client.iot_data["jadwal_aktif"] = database.ambil_jadwal()
        
        # Memori khusus untuk notifikasi agar kebal autorefresh
        if "notif_msg_jadwal" not in st.session_state:
            st.session_state.notif_msg_jadwal = None
            st.session_state.notif_type_jadwal = None
            st.session_state.notif_time_jadwal = 0

        jadwal_saat_ini = mqtt_client.iot_data["jadwal_aktif"]

        with st.container(border=True):
            st.info("Atur jam makan ikan secara otomatis (Format 24 Jam). Anda bisa menambah hingga 4 waktu pakan.", icon="ℹ️")
            
            # 3. Dynamic Scheduler (1 hingga 4 kali)
            jumlah_pakan = st.number_input("Frekuensi Pakan (Kali Sehari):", min_value=1, max_value=4, value=len(jadwal_saat_ini))

            # Sesuaikan array memori dengan jumlah input yang dipilih
            sementara = []
            for i in range(jumlah_pakan):
                if i < len(jadwal_saat_ini):
                    sementara.append(jadwal_saat_ini[i])
                else:
                    sementara.append("12:00") # Nilai bawaan jika slot baru ditambah

            with st.form("form_jadwal"):
                input_baru = []
                cols = st.columns(jumlah_pakan)
                
                for i, col in enumerate(cols):
                    with col:
                        # Bungkus setiap jadwal ke dalam satu kartu (container bergaris)
                        with st.container(border=True):
                            # Judul jadwal rata tengah
                            st.markdown(f"<div style='text-align:center; font-weight:bold; margin-bottom:5px;'>Jadwal {i+1}</div>", unsafe_allow_html=True)
                            
                            jam_awal, mnt_awal = sementara[i].split(":") if ":" in sementara[i] else ("00", "00")
                            
                            # -----------------------------------------------------
                            # INJEKSI BARU: CSS UNTUK MERAPATKAN INPUT & TANDA :
                            # -----------------------------------------------------
                            st.markdown(
                                """
                                <style>
                                    /* Wadah kustom untuk jadwal rapat */
                                    div.stTimeInput {
                                        margin-top: 5px;
                                    }
                                    /* Rapatkan kotak input jam & menit */
                                    div.stText input {
                                        text-align: center;
                                    }
                                </style>
                                """,
                                unsafe_allow_html=True,
                            )
                            
                            # Buat layout input dengan tanda : di tengah
                            sub_col1, sub_col_sep, sub_col2 = st.columns([3, 1, 3])
                            with sub_col1:
                                # Input Jam (label disembunyikan, teks rata tengah)
                                input_jam = st.text_input(f"Jam {i}", value=jam_awal, max_chars=2, key=f"jam_{i}", label_visibility="collapsed", placeholder="00")
                            with sub_col_sep:
                                # Tanda titik dua : kustom rata tengah
                                st.markdown("<div style='text-align:center; font-size:24px; font-weight:bold; margin-top:2px;'>:</div>", unsafe_allow_html=True)
                            with sub_col2:
                                # Input Menit (label disembunyikan, teks rata tengah)
                                input_mnt = st.text_input(f"Menit {i}", value=mnt_awal, max_chars=2, key=f"mnt_{i}", label_visibility="collapsed", placeholder="00")
                            
                            # Gabungkan kembali secara otomatis
                            input_baru.append(f"{input_jam.zfill(2)}:{input_mnt.zfill(2)}")
                
                submitted = st.form_submit_button("Perbarui Jadwal", type="primary", width="stretch")

        if submitted:
            import re, time
            valid = True
            for jam in input_baru:
                if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", jam):
                    valid = False
                    break
            
            if not valid:
                st.session_state.notif_msg_jadwal = "❌ Format waktu salah! Harap masukkan Jam (00-23) dan Menit (00-59)."
                st.session_state.notif_type_jadwal = "error"
                st.session_state.notif_time_jadwal = time.time()
            else:
                jadwal_payload = ",".join(input_baru)
                try:
                    if publish_mqtt(topic="PI_fishfeeder/control/jadwal", payload=jadwal_payload):
                        # --- INJEKSI SIMPAN KE DATABASE ---
                        import database
                        database.simpan_jadwal(jadwal_payload)
                        # ----------------------------------
                        
                        mqtt_client.iot_data["jadwal_aktif"] = input_baru
                        _add_log("JADWAL", f"Update -> {jadwal_payload}")
                        st.session_state.notif_msg_jadwal = f"✅ Jadwal berhasil diperbarui menjadi {jumlah_pakan} kali sehari: {jadwal_payload}"
                        st.session_state.notif_type_jadwal = "success"
                        st.session_state.notif_time_jadwal = time.time()
                    else:
                        st.session_state.notif_msg_jadwal = "❌ Gagal mengirim perintah ke broker MQTT."
                        st.session_state.notif_type_jadwal = "error"
                        st.session_state.notif_time_jadwal = time.time()
                except Exception as e:
                    st.session_state.notif_msg_jadwal = f"❌ Terjadi kesalahan: {e}"
                    st.session_state.notif_type_jadwal = "error"
                    st.session_state.notif_time_jadwal = time.time()

        # 5. Render Notifikasi (Di Luar Form, Di Dalam Container)
        import time
        with notif_jadwal:
            if st.session_state.get("notif_msg_jadwal"):
                if (time.time() - st.session_state.get("notif_time_jadwal", 0) < 4):
                    if st.session_state.notif_type_jadwal == "success":
                        st.success(st.session_state.notif_msg_jadwal)
                    else:
                        st.error(st.session_state.notif_msg_jadwal)
                else:
                    st.session_state.notif_msg_jadwal = None
                    st.session_state.notif_type_jadwal = None


# ─────────────────────────────────────────────
# Halaman 4: Log & Histori
# ─────────────────────────────────────────────
elif menu == "📝 Log & Histori":
    st.header("📝 Log & Histori Sistem")

    # 🛠️ DEV MODE: Kontrol Data Simulasi vs Realtime
    dev_col1, dev_col2 = st.columns(2)
    
    with dev_col1:
        if st.button("🛠️ Muat Data Simulasi (Preview Mode)", width="stretch"):
            import random, time
            from datetime import datetime, timedelta
            
            mqtt_client.iot_data["log_messages"] = [
                "Feeding via Jadwal", "FEED DITOLAK - STOK HABIS", 
                "Feeding via Dashboard", "FEED DITOLAK - STOK HABIS", "Feeding via Tombol Fisik"
            ]
            
            dummy_histori = []
            sekarang = datetime.now()
            
            # PAKSA LOOP 730 HARI (2 TAHUN KE BELAKANG)
            for i in range(730, -1, -1):
                tgl_dt = sekarang - timedelta(days=i)
                tgl_str = tgl_dt.strftime("%Y-%m-%d")
                
                base_freq = [1, 2, 0, 4, 1, 3, 2][tgl_dt.weekday()]
                
                for _ in range(base_freq):
                    dummy_histori.append({
                        "tanggal": tgl_str,
                        "waktu": f"{random.randint(8,20):02d}:{random.randint(0,59):02d}:{random.randint(0,59):02d}",
                        "status_pakan": "habis"
                    })
                
                for _ in range(1):
                    dummy_histori.append({
                        "tanggal": tgl_str,
                        "waktu": "08:00:00",
                        "status_pakan": "aman"
                    })
                    
            mqtt_client.iot_data["data_histori"] = dummy_histori
            st.toast("✅ Data simulasi 2 Tahun berhasil dimuat!", icon="🛠️")

    with dev_col2:
        if st.button("🧹 Bersihkan Data (Kembali ke Realtime)", width="stretch"):
            # Kosongkan memori array log dan histori
            mqtt_client.iot_data["log_messages"] = []
            mqtt_client.iot_data["data_histori"] = []
            st.toast("🧹 Memori dibersihkan. Sistem siap menerima data Real-time!", icon="✅")

    # [1] KONTINER GRAFIK ALTAIR
    with st.container(border=True):
        st.subheader("📈 Tren Frekuensi Pakan Habis")
        st.caption("Visualisasi seberapa sering wadah pakan kehabisan stok per harinya.")

        # LOGIKA HYBRID: Baca dari RAM (Simulasi) atau SQLite (Realtime)
        import database
        if mqtt_client.iot_data.get("data_histori"):
            df_histori = pd.DataFrame(mqtt_client.iot_data["data_histori"])
            st.warning("⚠️ Menampilkan Data Simulasi (Mockup di RAM)")
        else:
            df_histori = database.ambil_data_histori()

        if not df_histori.empty:
            # 1. Tambahkan Widget Pilihan Resolusi Waktu
            resolusi = st.radio("Pilih Resolusi Waktu:", ["Harian", "Bulanan", "Tahunan"], horizontal=True)
            
            # 2. Pastikan kolom tanggal berformat Datetime
            df_histori['tanggal_dt'] = pd.to_datetime(df_histori['tanggal'])
            
            if resolusi == "Harian":
                batas_waktu = datetime.now() - timedelta(days=14)
                df_histori = df_histori[df_histori['tanggal_dt'] >= batas_waktu]
                df_histori['periode'] = df_histori['tanggal_dt'].dt.strftime('%Y-%m-%d')
                df_histori['sort_key'] = df_histori['tanggal_dt'].dt.strftime('%Y-%m-%d')
            elif resolusi == "Bulanan":
                bulan_indo = {
                    1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 
                    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus", 
                    9: "September", 10: "Oktober", 11: "November", 12: "Desember"
                }
                df_histori['periode'] = df_histori['tanggal_dt'].dt.month.map(bulan_indo) + " " + df_histori['tanggal_dt'].dt.year.astype(str)
                # INJEKSI: Kunci rahasia berupa angka untuk memandu Altair
                df_histori['sort_key'] = df_histori['tanggal_dt'].dt.strftime('%Y-%m')
            else: # Tahunan
                df_histori['periode'] = df_histori['tanggal_dt'].dt.strftime('%Y')
                df_histori['sort_key'] = df_histori['tanggal_dt'].dt.strftime('%Y')
                
            df_habis = df_histori[df_histori['status_pakan'].str.lower() == 'habis']
            
            # Grouping menggunakan kombinasi sort_key dan periode
            df_tren = df_habis.groupby(['sort_key', 'periode']).size().reset_index(name='frekuensi')
            
            # Urutkan secara absolut berdasarkan angka (sort_key)
            df_tren = df_tren.sort_values('sort_key')
            
            # 1. Simpan urutan kronologis yang sudah benar ke dalam list
            urutan_kronologis = df_tren['periode'].tolist()
            
            # 2. Buang kolom sort_key agar tidak muncul di layar "View Data"
            df_tren = df_tren.drop(columns=['sort_key'])
            
            # 3. Ubah index dataframe agar dimulai dari 1
            df_tren.index = range(1, len(df_tren) + 1)
            
            if not df_tren.empty:
                max_freq = int(df_tren['frekuensi'].max()) if not df_tren.empty else 1
                tick_vals = list(range(0, max_freq + 1))
                
                chart = alt.Chart(df_tren).mark_bar(color="#7EC8E3").encode(
                    # Gunakan list urutan_kronologis yang kita simpan tadi untuk parameter sort
                    x=alt.X('periode:N', title='Waktu', axis=alt.Axis(labelAngle=0), sort=urutan_kronologis),
                    y=alt.Y('frekuensi:Q', title='Frekuensi Pakan Habis (Kali)', axis=alt.Axis(values=tick_vals, format='d'))
                ).properties(
                    height=350
                )
                st.altair_chart(chart, width="stretch")
            else:
                st.info("Belum ada data pakan habis untuk periode waktu ini.")
        else:
            st.info("Belum ada data historis yang dapat ditampilkan.")

    # [2] KONTAINER RIWAYAT PERINTAH
    with st.container(border=True):
        st.subheader("📋 Riwayat Perintah Sistem")
        
        import database
        # LOGIKA HYBRID: Dahulukan memori RAM jika mode simulasi aktif
        if mqtt_client.iot_data.get("log_messages"):
            for log in mqtt_client.iot_data["log_messages"]:
                st.code(log)
        else:
            # Ambil data murni dari SQLite jika mode simulasi kosong
            df_perintah = database.ambil_data_perintah()
            if not df_perintah.empty:
                for _, row in df_perintah.iterrows():
                    st.code(f"[{row['tanggal']} {row['waktu']}] {row['pemicu']}")
            else:
                st.info("Tidak ada data riwayat perintah di Database.")

    # [3] KONTAINER TABEL DATA STOK
    with st.container(border=True):
        st.subheader("📊 Log Data Stok dan Histori Pakan")

        # LOGIKA HYBRID: Baca dari RAM (Simulasi) atau SQLite (Realtime)
        import database
        if mqtt_client.iot_data.get("data_histori"):
            df_tabel_bawah = pd.DataFrame(mqtt_client.iot_data["data_histori"])
        else:
            df_tabel_bawah = database.ambil_data_histori()

        if not df_tabel_bawah.empty:
            df_tabel_bawah.index = range(1, len(df_tabel_bawah) + 1)
            st.dataframe(df_tabel_bawah, width="stretch")
        else:
            st.info("Tidak ada data historis di Database.")


# ─────────────────────────────────────────────
# Footer
# ─────────────────────────────────────────────
st.divider()
st.caption("Pakan Ikan IoT Dashboard • Diberdayakan oleh Streamlit & MQTT • Dibuat oleh [@haikalrth](https://github.com/haikalrth)")