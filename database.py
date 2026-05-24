import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime
import pytz

def get_connection():
    """Membuka koneksi langsung ke Cloud Database Supabase menggunakan URI dari secrets."""
    conn_url = st.secrets["connections"]["postgresql"]["url"]
    return psycopg2.connect(conn_url)

def init_db():
    """Membuat tabel-tabel terpusat di Supabase Cloud jika belum terbentuk."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Tabel Users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # 2. Tabel History Pakan
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history_pakan (
            id SERIAL PRIMARY KEY,
            tanggal TEXT NOT NULL,
            waktu TEXT NOT NULL,
            status_pakan TEXT NOT NULL
        )
    ''')
    
    # 3. Tabel Riwayat Perintah Sistem
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS riwayat_perintah (
            id SERIAL PRIMARY KEY,
            tanggal TEXT NOT NULL,
            waktu TEXT NOT NULL,
            pemicu TEXT NOT NULL
        )
    ''')
    
    # 4. Tabel Pengaturan Jadwal
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pengaturan_jadwal (
            id SERIAL PRIMARY KEY,
            jadwal_str TEXT NOT NULL
        )
    ''')
    
    # Seeding Akun Admin Default jika kosong
    cursor.execute('SELECT COUNT(*) FROM users')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO users (username, password) VALUES (%s, %s)', ('admin', 'admin123'))
        
    # Seeding Jadwal Default jika kosong
    cursor.execute('SELECT COUNT(*) FROM pengaturan_jadwal')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO pengaturan_jadwal (jadwal_str) VALUES (%s)', ('09:00,16:00',))
        
    conn.commit()
    cursor.close()
    conn.close()

def cek_login(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user is not None

def simpan_histori(status_pakan):
    wib = pytz.timezone("Asia/Jakarta")
    now = datetime.now(wib)
    tanggal = now.strftime("%Y-%m-%d")
    waktu = now.strftime("%H:%M:%S")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO history_pakan (tanggal, waktu, status_pakan)
        VALUES (%s, %s, %s)
    ''', (tanggal, waktu, status_pakan))
    conn.commit()
    cursor.close()
    conn.close()

def ambil_data_histori():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT tanggal, waktu, status_pakan FROM history_pakan ORDER BY tanggal DESC, waktu DESC')
    rows = cursor.fetchall()
    df = pd.DataFrame(rows, columns=['tanggal', 'waktu', 'status_pakan'])
    cursor.close()
    conn.close()
    return df

def simpan_perintah(pemicu):
    wib = pytz.timezone("Asia/Jakarta")
    now = datetime.now(wib)
    tanggal = now.strftime("%Y-%m-%d")
    waktu = now.strftime("%H:%M:%S")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO riwayat_perintah (tanggal, waktu, pemicu)
        VALUES (%s, %s, %s)
    ''', (tanggal, waktu, pemicu))
    conn.commit()
    cursor.close()
    conn.close()

def ambil_data_perintah():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT tanggal, waktu, pemicu FROM riwayat_perintah ORDER BY tanggal DESC, waktu DESC')
    rows = cursor.fetchall()
    df = pd.DataFrame(rows, columns=['tanggal', 'waktu', 'pemicu'])
    cursor.close()
    conn.close()
    return df

def simpan_jadwal(jadwal_str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE pengaturan_jadwal SET jadwal_str = %s WHERE id = 1', (jadwal_str,))
    conn.commit()
    cursor.close()
    conn.close()

def ambil_jadwal():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT jadwal_str FROM pengaturan_jadwal WHERE id = 1')
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row and row[0]:
        return row[0].split(',')
    return ["09:00", "16:00"]
