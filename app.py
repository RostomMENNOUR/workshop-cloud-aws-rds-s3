import os
import pymysql
import boto3
from botocore.exceptions import ClientError
from flask import Flask, request, render_template, redirect, url_for, send_from_directory

app = Flask(__name__)

# Dossier local pour le stockage des fichiers uploadés
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Variables de configuration (valeurs par défaut = Monolithe local)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "app_user")
DB_PASS = os.getenv("DB_PASS", "LocalPass123!")
DB_NAME = os.getenv("DB_NAME", "medapp_db")
S3_BUCKET = os.getenv("S3_BUCKET", "")

def get_db():
    return pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        cursorclass=pymysql.cursors.DictCursor
    )

def save_uploaded_file(file_obj, filename):
    """Stockage local si S3_BUCKET n'est pas défini, sinon envoi sur S3"""
    if not S3_BUCKET:
        dest_path = os.path.join(UPLOAD_FOLDER, filename)
        file_obj.save(dest_path)
        return filename
    
    # Mode découplé (S3)
    s3 = boto3.client('s3')
    s3.upload_fileobj(file_obj, S3_BUCKET, filename)
    return filename

def generate_file_link(filename):
    """Génère un lien direct local ou une URL présignée S3"""
    if not S3_BUCKET:
        return url_for('uploaded_file', filename=filename)
    
    # Mode découplé (URL présignée temporaire 5 min)
    s3 = boto3.client('s3')
    try:
        return s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET, 'Key': filename},
            ExpiresIn=300
        )
    except ClientError:
        return "#erreur-s3"

@app.route("/")
def index():
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM records ORDER BY id DESC")
        records = cur.fetchall()
    conn.close()

    for r in records:
        r['file_url'] = generate_file_link(r['file_key'])

    return render_template(
        "index.html",
        records=records,
        s3_bucket=S3_BUCKET,
        db_host=DB_HOST
    )

@app.route("/add", methods=["POST"])
def add_patient():
    patient = request.form["patient_name"]
    diag = request.form["diagnosis"]
    file = request.files["file"]

    if file and file.filename != "":
        saved_key = save_uploaded_file(file, file.filename)
        conn = get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO records (patient_name, diagnosis, file_key) VALUES (%s, %s, %s)",
                (patient, diag, saved_key)
            )
        conn.commit()
        conn.close()

    return redirect(url_for("index"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """Sert les fichiers statiques locaux tant qu'on est en monolithe"""
    return send_from_directory(UPLOAD_FOLDER, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)