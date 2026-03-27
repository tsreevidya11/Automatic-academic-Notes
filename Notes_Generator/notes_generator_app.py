import streamlit as st
import mysql.connector
from datetime import datetime
from google import genai
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from docx import Document
import io

# ------------------- PAGE CONFIG -------------------
st.set_page_config(page_title="📚 Notes Generator", page_icon="📚", layout="centered")

# ------------------- GEMINI SETUP -------------------
api_key = st.secrets["general"]["GOOGLE_API_KEY"]
client = genai.Client(api_key=api_key)

# ------------------- MYSQL CONNECTION -------------------
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="root",   # 🔴 change this
    database="notes_app"
)
cursor = conn.cursor()

# ------------------- TABLE CREATION -------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS notes_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title TEXT,
    lecture_text TEXT,
    generated_notes TEXT,
    difficulty VARCHAR(50),
    created_at DATETIME,
    username VARCHAR(100)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE,
    password VARCHAR(100),
    role VARCHAR(20)
)
""")
conn.commit()

# ------------------- DEFAULT ADMIN -------------------
cursor.execute("SELECT * FROM users WHERE username=%s", ("admin",))
if cursor.fetchone() is None:
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        ("admin", "admin123", "admin")
    )
    conn.commit()

# ------------------- FUNCTIONS -------------------
def generate_notes_with_gemini(text: str, difficulty: str) -> str:
    prompt = f"""
You are an academic notes generator for students.
Convert the following lecture text into structured academic notes.

Difficulty Level: {difficulty}

Output format:
Title:
Introduction:
Definitions:
Key Concepts:
Examples:
Tables:
Diagrams:
Formulas:
Exam Questions:
Summary:

Lecture Text:
{text}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


def save_notes(title, lecture_text, notes, difficulty, username):
    cursor.execute("""
    INSERT INTO notes_data (title, lecture_text, generated_notes, difficulty, created_at, username)
    VALUES (%s, %s, %s, %s, %s, %s)
    """, (title, lecture_text, notes, difficulty, datetime.now(), username))
    conn.commit()


def fetch_notes(username, search=""):
    if search.strip():
        cursor.execute("""
        SELECT id, title, lecture_text, generated_notes, difficulty, created_at, username
        FROM notes_data
        WHERE username=%s AND 
        (title LIKE %s OR lecture_text LIKE %s OR generated_notes LIKE %s)
        ORDER BY id DESC
        """, (username, f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
        SELECT id, title, lecture_text, generated_notes, difficulty, created_at, username
        FROM notes_data
        WHERE username=%s
        ORDER BY id DESC
        """, (username,))
    return cursor.fetchall()


def delete_note(note_id):
    cursor.execute("DELETE FROM notes_data WHERE id=%s", (note_id,))
    conn.commit()


def login_user(username, password):
    cursor.execute("SELECT role FROM users WHERE username=%s AND password=%s", (username, password))
    result = cursor.fetchone()
    return result[0] if result else None


def register_user(username, password):
    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, password, "user")
        )
        conn.commit()
        return True
    except:
        return False


# ------------------- FILE GENERATION -------------------
def generate_pdf(notes: str):
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    story = []

    for line in notes.split("\n"):
        if line.strip():
            story.append(Paragraph(line, styles["BodyText"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    buffer.seek(0)
    return buffer


def generate_docx(notes: str):
    buffer = io.BytesIO()
    doc = Document()

    for line in notes.split("\n"):
        if line.strip():
            doc.add_paragraph(line)

    doc.save(buffer)
    buffer.seek(0)
    return buffer


# ------------------- SESSION -------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

# ------------------- LOGIN PAGE -------------------
if not st.session_state.logged_in:
    st.title("🔐 Login - Notes Generator")
    choice = st.radio("Select Option", ["Login", "Register"])

    if choice == "Login":
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            role = login_user(username, password)
            if role:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.role = role
                st.success(f"Welcome {username}")
                st.rerun()
            else:
                st.error("Invalid credentials")

    else:
        new_user = st.text_input("New Username")
        new_pass = st.text_input("New Password", type="password")

        if st.button("Register"):
            if register_user(new_user, new_pass):
                st.success("Registered successfully")
            else:
                st.error("Username already exists")

    st.stop()

# ------------------- MAIN APP -------------------
st.title("📚 Automatic Notes Generator")
st.write(f"Welcome {st.session_state.username}")

if st.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()

tab1, tab2 = st.tabs(["Generate Notes", "History"])

# ------------------- TAB 1 -------------------
with tab1:
    title = st.text_input("Title")
    text = st.text_area("Lecture Text")
    difficulty = st.selectbox("Difficulty", ["Simple", "Medium", "Exam-oriented"])

    if st.button("Generate"):
        if title and text:
            notes = generate_notes_with_gemini(text, difficulty)
            st.write(notes)

            save_notes(title, text, notes, difficulty, st.session_state.username)

            st.download_button("Download PDF", generate_pdf(notes), "notes.pdf")
            st.download_button("Download DOCX", generate_docx(notes), "notes.docx")
        else:
            st.warning("Fill all fields")

# ------------------- TAB 2 -------------------
with tab2:
    search = st.text_input("Search")

    rows = fetch_notes(st.session_state.username, search)

    for row in rows:
        note_id, title, lec, notes, diff, time, user = row

        with st.expander(f"{title} | {diff} | {time}"):
            st.write(notes)

            st.download_button("PDF", generate_pdf(notes), key=f"pdf{note_id}")
            st.download_button("DOCX", generate_docx(notes), key=f"docx{note_id}")

            if st.session_state.role == "admin":
                if st.button("Delete", key=f"del{note_id}"):
                    delete_note(note_id)
                    st.rerun()
