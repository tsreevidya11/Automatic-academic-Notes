import streamlit as st
import sqlite3
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

# ------------------- DATABASE SETUP -------------------
conn = sqlite3.connect("notes.db", check_same_thread=False)
cursor = conn.cursor()

# Notes Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS notes_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    lecture_text TEXT,
    generated_notes TEXT,
    created_at TEXT
)
""")
conn.commit()

# Add difficulty column if not exists
try:
    cursor.execute("ALTER TABLE notes_data ADD COLUMN difficulty TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

# Add username column if not exists
try:
    cursor.execute("ALTER TABLE notes_data ADD COLUMN username TEXT")
    conn.commit()
except sqlite3.OperationalError:
    pass

# Users Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password TEXT,
    role TEXT
)
""")
conn.commit()

# Create default admin if not exists
cursor.execute("SELECT * FROM users WHERE username='admin'")
if cursor.fetchone() is None:
    cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                   ("admin", "admin123", "admin"))
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
    VALUES (?, ?, ?, ?, ?, ?)
    """, (title, lecture_text, notes, difficulty,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username))
    conn.commit()


def fetch_notes(username, role, search=""):
    if search.strip():
        cursor.execute("""
        SELECT id, title, lecture_text, generated_notes, difficulty, created_at, username
        FROM notes_data
        WHERE username = ?
        AND (title LIKE ? OR lecture_text LIKE ? OR generated_notes LIKE ?)
        ORDER BY id DESC
        """, (username, f"%{search}%", f"%{search}%", f"%{search}%"))
    else:
        cursor.execute("""
        SELECT id, title, lecture_text, generated_notes, difficulty, created_at, username
        FROM notes_data
        WHERE username = ?
        ORDER BY id DESC
        """, (username,))
    return cursor.fetchall()


def delete_note(note_id):
    cursor.execute("DELETE FROM notes_data WHERE id = ?", (note_id,))
    conn.commit()


def login_user(username, password):
    cursor.execute("SELECT role FROM users WHERE username=? AND password=?", (username, password))
    result = cursor.fetchone()
    return result[0] if result else None


def register_user(username, password, role="user"):
    try:
        cursor.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                       (username, password, role))
        conn.commit()
        return True
    except:
        return False


# ------------------- PDF & DOCX GENERATION (IN MEMORY) -------------------
def generate_pdf_in_memory(notes: str):
    pdf_buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=A4)
    story = []

    for line in notes.split("\n"):
        if line.strip():
            story.append(Paragraph(line, styles["BodyText"]))
            story.append(Spacer(1, 6))

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer


def generate_docx_in_memory(notes: str):
    docx_buffer = io.BytesIO()
    doc = Document()

    for line in notes.split("\n"):
        if line.strip():
            doc.add_paragraph(line)

    doc.save(docx_buffer)
    docx_buffer.seek(0)
    return docx_buffer


# ------------------- LOGIN SYSTEM -------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None

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
                st.session_state.role = role
                st.session_state.username = username
                st.success(f"✅ Welcome {username} ({role})")
                st.rerun()
            else:
                st.error("❌ Invalid username or password")

    else:
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")

        if st.button("Register"):
            if register_user(new_username, new_password):
                st.success("✅ Registered Successfully! Now login.")
            else:
                st.error("❌ Username already exists!")

    st.stop()

# ------------------- MAIN UI -------------------
st.title("📚 Automatic Academic Notes Generator")
st.write(f"Welcome **{st.session_state.username}** 👋 | Role: **{st.session_state.role}**")

if st.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.rerun()

tab1, tab2 = st.tabs(["📝 Generate Notes", "📂 Notes History"])

# ------------------- TAB 1 -------------------
with tab1:
    st.subheader("📝 Generate Notes")
    title = st.text_input("Topic / Title", placeholder="Enter topic title...")
    lecture_text = st.text_area("Lecture Text", height=250, placeholder="Paste lecture text here...")
    difficulty = st.selectbox("🎯 Select Difficulty Level", ["Simple", "Medium", "Exam-oriented"])

    if st.button("✨ Generate Notes"):
        if not title.strip() or not lecture_text.strip():
            st.warning("⚠️ Please fill all fields.")
        else:
            with st.spinner("Generating notes using Gemini..."):
                notes = generate_notes_with_gemini(lecture_text, difficulty)

            st.success("✅ Notes Generated Successfully!")
            st.subheader("📌 Generated Notes")
            st.write(notes)

            # Save notes user-wise
            save_notes(title, lecture_text, notes, difficulty, st.session_state.username)

            safe_title = title.replace(" ", "_")
            pdf_filename = f"{safe_title}_notes.pdf"
            docx_filename = f"{safe_title}_notes.docx"

            # Generate files in memory (NO files saved on disk)
            pdf_buffer = generate_pdf_in_memory(notes)
            docx_buffer = generate_docx_in_memory(notes)

            st.download_button("📥 Download PDF", pdf_buffer, file_name=pdf_filename, mime="application/pdf")
            st.download_button("📥 Download DOCX", docx_buffer, file_name=docx_filename,
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

# ------------------- TAB 2 -------------------
with tab2:
    st.subheader("📂 Saved Notes History")
    search = st.text_input("🔍 Search Notes", placeholder="Type keyword...")

    rows = fetch_notes(st.session_state.username, st.session_state.role, search)

    if not rows:
        st.info("No notes found yet. Generate notes in the first tab.")
    else:
        for row in rows:
            note_id, note_title, lec_text, gen_notes, diff, created_at, username = row

            with st.expander(f"📌 {note_title} | 🎯 {diff} | 🕒 {created_at} | 👤 {username} | ID: {note_id}"):
                st.markdown("### 🧾 Lecture Text (Preview)")
                st.write(lec_text[:500] + ("..." if len(lec_text) > 500 else ""))

                st.markdown("### ✅ Generated Notes")
                st.write(gen_notes)

                safe_title = note_title.replace(" ", "_")
                pdf_file = f"{safe_title}_ID{note_id}.pdf"
                docx_file = f"{safe_title}_ID{note_id}.docx"

                # Generate in memory
                pdf_buffer = generate_pdf_in_memory(gen_notes)
                docx_buffer = generate_docx_in_memory(gen_notes)

                st.download_button(f"📥 Download PDF", pdf_buffer, file_name=pdf_file,
                                   mime="application/pdf", key=f"pdf_{note_id}")

                st.download_button(f"📥 Download DOCX", docx_buffer, file_name=docx_file,
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                   key=f"docx_{note_id}")

                # Admin delete option (Admin deletes only their notes shown)
                if st.session_state.role == "admin":
                    if st.button(f"🗑 Delete Note (ID: {note_id})", key=f"delete_{note_id}"):
                        delete_note(note_id)
                        st.warning("Deleted successfully! Refreshing...")
                        st.rerun()
