import streamlit as st
from supabase import create_client
import pandas as pd
from datetime import datetime
import pytz

# Inisialisasi client Supabase menggunakan URL dan Key dari secrets
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

def init_db():
    # Pembuatan tabel tidak didukung via ORM Supabase Python client.
    # Tabel harus sudah dibuat secara manual di dashboard Supabase.
    pass

def cek_login(username, password):
    try:
        response = supabase.table("users").select("*").eq("username", username).eq("password", password).execute()
        return len(response.data) > 0
    except Exception as e:
        st.error(f"DEBUG: [API ERROR] {e}")
        return False

def simpan_histori(status_pakan):
    try:
        wib = pytz.timezone("Asia/Jakarta")
        now = datetime.now(wib)
        tanggal = now.strftime("%Y-%m-%d")
        waktu = now.strftime("%H:%M:%S")
        
        data = {
            "tanggal": tanggal,
            "waktu": waktu,
            "status_pakan": status_pakan
        }
        supabase.table("history_pakan").insert(data).execute()
    except Exception as e:
        print(f"Error simpan_histori: {e}")

def ambil_data_histori():
    try:
        # Order by tanggal DESC, waktu DESC
        response = supabase.table("history_pakan").select("tanggal, waktu, status_pakan").order("tanggal", desc=True).order("waktu", desc=True).execute()
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame(columns=["tanggal", "waktu", "status_pakan"])
    except Exception as e:
        print(f"Error ambil_data_histori: {e}")
        return pd.DataFrame(columns=["tanggal", "waktu", "status_pakan"])

def simpan_perintah(pemicu):
    try:
        wib = pytz.timezone("Asia/Jakarta")
        now = datetime.now(wib)
        tanggal = now.strftime("%Y-%m-%d")
        waktu = now.strftime("%H:%M:%S")
        
        data = {
            "tanggal": tanggal,
            "waktu": waktu,
            "pemicu": pemicu
        }
        supabase.table("riwayat_perintah").insert(data).execute()
    except Exception as e:
        print(f"Error simpan_perintah: {e}")

def ambil_data_perintah():
    try:
        response = supabase.table("riwayat_perintah").select("tanggal, waktu, pemicu").order("tanggal", desc=True).order("waktu", desc=True).execute()
        if response.data:
            return pd.DataFrame(response.data)
        else:
            return pd.DataFrame(columns=["tanggal", "waktu", "pemicu"])
    except Exception as e:
        print(f"Error ambil_data_perintah: {e}")
        return pd.DataFrame(columns=["tanggal", "waktu", "pemicu"])

def simpan_jadwal(jadwal_str):
    try:
        # Gunakan upsert untuk baris ID 1 (menambah jika belum ada, menimpa jika ada)
        supabase.table("pengaturan_jadwal").upsert({"id": 1, "jadwal_str": jadwal_str}).execute()
    except Exception as e:
        print(f"Error simpan_jadwal: {e}")

def ambil_jadwal():
    try:
        response = supabase.table("pengaturan_jadwal").select("jadwal_str").eq("id", 1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]["jadwal_str"].split(',')
        return ["09:00", "16:00"]
    except Exception as e:
        print(f"Error ambil_jadwal: {e}")
        return ["09:00", "16:00"]
