from flask import Flask, render_template, request, redirect, session, send_from_directory
import os
import sqlite3
from datetime import datetime
from PyPDF2 import PdfReader

# ================= PATH =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "print_easy.db")

template_dir = os.path.join(BASE_DIR, "../frontend")
upload_dir = os.path.join(BASE_DIR, "../uploads")

app = Flask(__name__, template_folder=template_dir)
app.secret_key = "secret123"

app.config["UPLOAD_FOLDER"] = upload_dir
os.makedirs(upload_dir, exist_ok=True)

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            email TEXT UNIQUE,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shopkeepers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            password TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS print_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            filename TEXT,
            pages INTEGER,
            copies INTEGER,
            print_type TEXT,
            binding TEXT,
            price INTEGER,
            status TEXT,
            upload_time TEXT
        )
    """)

    # Default shopkeeper
    cursor.execute("SELECT * FROM shopkeepers")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO shopkeepers (username, password) VALUES (?, ?)", ("admin", "123"))

    conn.commit()
    conn.close()

init_db()

# ================= HOME =================
@app.route("/")
def start():
    return render_template("student/login.html")


# ================= SIGNUP =================
@app.route("/signup")
def signup_page():
    return render_template("student/signup.html")


@app.route("/signup", methods=["POST"])
def signup():
    name = request.form["name"]
    email = request.form["email"]
    password = request.form["password"]
    confirm = request.form["confirm_password"]

    if password != confirm:
        return "Password mismatch"

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO students (name, email, password) VALUES (?, ?, ?)",
            (name, email, password)
        )
        conn.commit()
    except:
        return "Email already exists"

    conn.close()
    return redirect("/")


# ================= STUDENT LOGIN =================
@app.route("/student-login", methods=["POST"])
def student_login():
    email = request.form["email"]
    password = request.form["password"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE email=? AND password=?", (email, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session["student"] = user[1]   # name
        session["email"] = user[2]     # email
        return redirect("/dashboard")

    return "Invalid login"


# ================= DASHBOARD =================
@app.route("/dashboard")
def dashboard():
    if "student" not in session:
        return redirect("/")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, filename, status, upload_time 
        FROM print_requests 
        WHERE student_name=? 
        ORDER BY id DESC
    """, (session["student"],))

    orders = cursor.fetchall()
    conn.close()

    return render_template(
        "student/dashboard.html",
        student_name=session["student"],
        orders=orders
    )


# ================= PREVIEW =================
@app.route("/preview", methods=["POST"])
def preview():
    if "student" not in session:
        return redirect("/")

    file = request.files["file"]

    filename = str(datetime.now().timestamp()) + "_" + file.filename.replace(" ", "_")
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)

    reader = PdfReader(filepath)
    pages = len(reader.pages)

    copies = int(request.form["copies"])
    print_type = request.form["print_type"]
    binding = request.form["binding"]

    price = pages * copies * (2 if print_type == "bw" else 5)
    if binding == "spiral":
        price += 20

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, filename, status, upload_time 
        FROM print_requests 
        WHERE student_name=?
        ORDER BY id DESC
    """, (session["student"],))
    orders = cursor.fetchall()
    conn.close()

    return render_template(
        "student/dashboard.html",
        student_name=session["student"],
        orders=orders,
        filename=filename,
        pages=pages,
        copies=copies,
        print_type=print_type,
        binding=binding,
        price=price,
        show_payment=True
    )


# ================= PAYMENT (LOGIN BASED) =================
@app.route("/pay", methods=["POST"])
def pay():
    if "student" not in session:
        return redirect("/")

    try:
        data = request.form
        email = data.get("email")
        password = data.get("password")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # ✅ Verify user credentials
        cursor.execute(
            "SELECT * FROM students WHERE email=? AND password=?",
            (email, password)
        )
        user = cursor.fetchone()

        if not user:
            conn.close()
            return "invalid"

        # ✅ Save request
        cursor.execute("""
            INSERT INTO print_requests
            (student_name, filename, pages, copies, print_type, binding, price, status, upload_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session["student"],
            data.get("filename"),
            int(data.get("pages")),
            int(data.get("copies")),
            data.get("print_type"),
            data.get("binding"),
            int(data.get("price")),
            "Pending",
            datetime.now().strftime("%d-%m-%Y %H:%M")
        ))

        conn.commit()
        conn.close()

        return "success"

    except Exception as e:
        print("PAY ERROR:", e)
        return "error"


# ================= SHOPKEEPER =================
@app.route("/shopkeeper-login")
def shopkeeper_login_page():
    return render_template("shopkeeper/login.html")


@app.route("/shopkeeper-login", methods=["POST"])
def shopkeeper_login():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM shopkeepers WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        session["shopkeeper"] = username
        return redirect("/home")

    return "Invalid login"


@app.route("/home")
def home():
    if "shopkeeper" not in session:
        return redirect("/shopkeeper-login")
    return render_template("shopkeeper/home.html")


@app.route("/shopkeeper-dashboard")
def shopkeeper_dashboard():
    if "shopkeeper" not in session:
        return redirect("/shopkeeper-login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM print_requests WHERE status='Pending'")
    data = cursor.fetchall()

    conn.close()

    return render_template("shopkeeper/dashboard.html", requests=data)


# ================= SHOPKEEPER SIGNUP =================
@app.route("/shopkeeper-signup")
def shopkeeper_signup_page():
    return render_template("shopkeeper/signup.html")


@app.route("/shopkeeper-signup", methods=["POST"])
def shopkeeper_signup():
    username = request.form["username"]
    password = request.form["password"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT INTO shopkeepers (username, password) VALUES (?, ?)",
            (username, password)
        )
        conn.commit()
    except:
        conn.close()
        return "Username already exists ❌"

    conn.close()
    return redirect("/shopkeeper-login")


# ================= COMPLETE PRINT =================
@app.route("/print/<int:id>")
def print_file(id):
    if "shopkeeper" not in session:
        return redirect("/shopkeeper-login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("UPDATE print_requests SET status='Completed' WHERE id=?", (id,))
    conn.commit()
    conn.close()

    return redirect("/shopkeeper-dashboard")


# ================= INVOICE =================
@app.route("/invoice")
def invoice():
    if "shopkeeper" not in session:
        return redirect("/shopkeeper-login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT student_name, filename, pages, copies, print_type, price, upload_time
        FROM print_requests WHERE status='Completed'
    """)

    data = cursor.fetchall()
    total = sum(int(row[5]) for row in data) if data else 0

    conn.close()

    return render_template("shopkeeper/invoice.html", invoices=data, total=total)

##############earning#################
@app.route("/earnings")
def earnings():
    if "shopkeeper" not in session:
        return redirect("/shopkeeper-login")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # DAILY
    cursor.execute("""
        SELECT substr(upload_time,1,10), SUM(price), COUNT(*)
        FROM print_requests 
        WHERE status='Completed'
        GROUP BY substr(upload_time,1,10)
    """)
    daily_data = cursor.fetchall() or []

    # MONTHLY (FIXED SORTING)
    cursor.execute("""
        SELECT 
            substr(upload_time,4,7) as month,
            SUM(price)
        FROM print_requests 
        WHERE status='Completed'
        GROUP BY month
        ORDER BY substr(upload_time,7,4), substr(upload_time,4,2)
    """)
    monthly_rows = cursor.fetchall() or []

    conn.close()

    # CONVERT FOR CHART
    monthly_labels = []
    monthly_values = []

    for row in monthly_rows:
        monthly_labels.append(row[0])
        monthly_values.append(row[1])

    return render_template(
        "shopkeeper/earnings.html",
        daily_data=daily_data,
        monthly_labels=monthly_labels,
        monthly_values=monthly_values
    )
 

# ================= DOWNLOAD =================
@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(upload_dir, filename)


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)