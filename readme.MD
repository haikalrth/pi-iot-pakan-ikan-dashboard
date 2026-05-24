# 🐟 Pakan Ikan IoT Dashboard

Antarmuka (*dashboard*) berbasis web untuk pemantauan (*monitoring*) dan kendali jarak jauh perangkat pemberi pakan ikan otomatis (*Fish Feeder*). Sistem ini mengintegrasikan mikrokontroler dengan protokol MQTT dan infrastruktur *Cloud Database* untuk pencatatan log operasional secara *real-time* dan permanen.

Penelitian ini dikembangkan sebagai bagian dari tugas Penulisan Ilmiah pada program studi Informatika di Universitas Gunadarma.

## 🏗️ Arsitektur Teknologi
Sistem ini dibangun menggunakan arsitektur *Software-as-a-Service* (SaaS) ringan dengan tumpukan teknologi berikut:
* **Frontend/Backend:** Python 3, Streamlit, Pandas, Altair
* **Komunikasi IoT:** Protokol MQTT (Paho-MQTT via broker HiveMQ)
* **Cloud Database:** PostgreSQL (Supabase) via `psycopg2-binary`

## ✨ Fitur Utama Sistem
1. **Pemantauan Real-Time:** Menampilkan status ketersediaan pakan dan stempel waktu (*timestamp*) dari alat fisik tanpa *delay*.
2. **Kemandirian Algoritma (Anti-Spam Filter):** Sistem memfilter ratusan data sensor per menit dan hanya mencatat anomali/perubahan status fisik ke dalam *database*.
3. **Kendali Jarak Jauh & Penjadwalan:** Memungkinkan pengguna memberikan pakan secara manual atau mengatur ulang jadwal otomatis langsung dari *browser*.
4. **Audit Trail (Log Persisten):** Seluruh riwayat eksekusi servo (baik karena jadwal maupun kendali manual) terekam abadi di PostgreSQL *Cloud* untuk analisis forensik dan evaluasi performa alat.

## 🔒 Catatan Keamanan
Repositori ini hanya berisi kode sumber untuk antarmuka pengguna dan logika integrasi *database*. Kredensial *Cloud Database* dan parameter jalur komunikasi MQTT disimpan secara terpisah melalui variabel lingkungan (*Environment Variables*) untuk memastikan keamanan data tingkat produksi.

---
*Diberdayakan oleh Streamlit & MQTT* • [@haikalrth](https://github.com/haikalrth)
