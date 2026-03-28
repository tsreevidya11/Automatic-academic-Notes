import streamlit as st
import mysql.connector
from datetime import datetime
from google import genai
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from docx import Document
import io
import bcrypt

# ------------------- PAGE CONFIG -------------------
st.set_page_config(page_title="📚 Notes Generator", page_icon="📚")

# ------------------- SECRETS -------------------
try:
    api_key = st.secrets["general"]["GOOGLE_API_KEY"]
    db_password = st.secrets["mysql"]["password"]
except:
    st.error("⚠️ Add secrets.toml")
    st.stop()

# ------------------- GEMINI -------------------
client = genai.Client(api_key=api_key)

# ------------------- DATABASE -------------------
try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=db_password,
        database="notes_app"
    )
    cursor = conn.cursor()
except:
    st.error("❌ MySQL connection failed")
    st.stop()

# ------------------- TABLES -------------------
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(100) UNIQUE,
    password VARCHAR(255),
    role VARCHAR(20)
)
""")

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
conn.commit()

# ------------------- PASSWORD FUNCTIONS -------------------
def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password, hashed):
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except:
        return password == hashed  # fallback (old data)

# ------------------- DEFAULT ADMIN -------------------
cursor.execute("SELECT * FROM users WHERE username=%s", ("admin",))
if cursor.fetchone() is None:
    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        ("admin", hash_password("admin123"), "admin")
    )
    conn.commit()

# ------------------- AUTH -------------------
def login_user(username, password):
    cursor.execute("SELECT password, role FROM users WHERE username=%s", (username,))
    result = cursor.fetchone()

    if result and check_password(password, result[0]):
        return result[1]
    return None

def register_user(username, password):
    try:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
            (username, hash_password(password), "user")
        )
        conn.commit()
        return True
    except:
        return False

# ------------------- GEMINI FUNCTION -------------------
def generate_notes(text, difficulty):
    prompt = f"""
Convert this lecture into structured notes.

Difficulty: {difficulty}

Include:
Title, Introduction, Definitions, Key Concepts, Examples, Tables,
Diagrams, Formulas, Exam Questions, Summary

{text}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

# ------------------- DATABASE -------------------
def save_notes(title, text, notes, difficulty, user):
    cursor.execute("""
    INSERT INTO notes_data (title, lecture_text, generated_notes, difficulty, created_at, username)
    VALUES (%s,%s,%s,%s,%s,%s)
    """, (title, text, notes, difficulty, datetime.now(), user))
    conn.commit()

def fetch_notes(user, search=""):
    if search:
        cursor.execute("""
        SELECT * FROM notes_data
        WHERE username=%s AND (title LIKE %s OR generated_notes LIKE %s)
        ORDER BY id DESC
        """, (user, f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("SELECT * FROM notes_data WHERE username=%s ORDER BY id DESC", (user,))
    return cursor.fetchall()

def delete_note(id):
    cursor.execute("DELETE FROM notes_data WHERE id=%s", (id,))
    conn.commit()

# ------------------- FILE EXPORT -------------------
def generate_pdf(notes):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []

    for line in notes.split("\n"):
        story.append(Paragraph(line, styles["BodyText"]))
        story.append(Spacer(1, 6))

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_docx(notes):
    buffer = io.BytesIO()
    doc = Document()

    for line in notes.split("\n"):
        doc.add_paragraph(line)

    doc.save(buffer)
    buffer.seek(0)
    return buffer

# ------------------- SESSION -------------------
if "login" not in st.session_state:
    st.session_state.login = False

# ------------------- LOGIN -------------------
if not st.session_state.login:
    st.title("🔐 Login")

    option = st.radio("Choose", ["Login", "Register"])

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if option == "Login":
        if st.button("Login"):
            role = login_user(username, password)
            if role:
                st.session_state.login = True
                st.session_state.user = username
                st.session_state.role = role
                st.success("Login successful")
                st.rerun()
            else:
                st.error("Invalid credentials")

    else:
        if st.button("Register"):
            if register_user(username, password):
                st.success("Registered")
            else:
                st.error("User exists")

    st.stop()

# ------------------- MAIN -------------------
st.title("📚 Notes Generator")
st.write(f"Welcome {st.session_state.user}")

if st.button("Logout"):
    st.session_state.login = False
    st.rerun()

tab1, tab2 = st.tabs(["Generate", "History"])

# ------------------- GENERATE -------------------
with tab1:
    title = st.text_input("Title")
    text = st.text_area("Lecture Text")
    difficulty = st.selectbox("Difficulty", ["Simple", "Medium", "Exam-oriented"])

    if st.button("Generate"):
        if title and text:
            with st.spinner("Generating..."):
                notes = generate_notes(text, difficulty)

            st.markdown(notes)
            save_notes(title, text, notes, difficulty, st.session_state.user)

            st.download_button("PDF", generate_pdf(notes), "notes.pdf")
            st.download_button("DOCX", generate_docx(notes), "notes.docx")
        else:
            st.warning("Fill all fields")

# ------------------- HISTORY -------------------
with tab2:
    search = st.text_input("Search")

    rows = fetch_notes(st.session_state.user, search)

    for row in rows:
        id, title, lec, notes, diff, time, user = row

        with st.expander(f"{title} | {diff} | {time}"):
            st.markdown(notes)

            st.download_button("PDF", generate_pdf(notes), key=f"p{id}")
            st.download_button("DOCX", generate_docx(notes), key=f"d{id}")

            if st.session_state.role == "admin":
                if st.button("Delete", key=f"x{id}"):
                    delete_note(id)
                    st.rerun()
