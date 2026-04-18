import base64
import html
import json
import os
import sqlite3
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR))
DB_PATH = DATA_DIR / "cincel_academico.db"
STATIC_FILES = {
    "/": ("main.html", "text/html; charset=utf-8"),
    "/main.html": ("main.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                parent_name TEXT NOT NULL,
                whatsapp TEXT NOT NULL,
                subject TEXT NOT NULL,
                grade_level TEXT,
                institution TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS academic_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                session_date TEXT NOT NULL,
                session_number INTEGER,
                attendance TEXT NOT NULL,
                grade REAL,
                topic TEXT,
                observation TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            );
            """
        )


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def download_response(handler, body, content_type, filename):
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_body(handler):
    content_length = int(handler.headers.get("Content-Length", "0"))
    raw_body = handler.rfile.read(content_length) if content_length else b"{}"
    return json.loads(raw_body.decode("utf-8"))


def validate_whatsapp_number(number):
    normalized = (number or "").strip().replace(" ", "")
    if not normalized.startswith("+") or not normalized[1:].isdigit():
        raise ValueError("El numero de WhatsApp debe incluir indicativo internacional, por ejemplo +573001234567.")
    return normalized


def normalize_student(payload):
    name = (payload.get("name") or "").strip()
    parent_name = (payload.get("parent_name") or "").strip()
    whatsapp = validate_whatsapp_number(payload.get("whatsapp"))
    subject = (payload.get("subject") or "").strip()
    grade_level = (payload.get("grade_level") or "").strip()
    institution = (payload.get("institution") or "").strip()

    if not name or not parent_name or not subject:
        raise ValueError("Nombre del estudiante, acudiente y materia son obligatorios.")

    return {
        "name": name,
        "parent_name": parent_name,
        "whatsapp": whatsapp,
        "subject": subject,
        "grade_level": grade_level,
        "institution": institution,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def normalize_record(payload):
    student_id = payload.get("student_id")
    session_date = (payload.get("session_date") or "").strip()
    attendance = (payload.get("attendance") or "").strip()
    topic = (payload.get("topic") or "").strip()
    observation = (payload.get("observation") or "").strip()
    session_number = payload.get("session_number")
    grade = payload.get("grade")

    if not student_id:
        raise ValueError("Debes seleccionar un estudiante.")
    if not session_date:
        raise ValueError("La fecha del registro es obligatoria.")
    if not attendance:
        raise ValueError("La asistencia es obligatoria.")

    try:
        datetime.strptime(session_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from exc

    if session_number in ("", None):
        session_number = None
    else:
        session_number = int(session_number)
        if session_number < 1:
            raise ValueError("La sesion debe ser mayor o igual a 1.")

    if grade in ("", None):
        grade = None
    else:
        grade = float(grade)
        if grade < 0 or grade > 100:
            raise ValueError("La nota debe estar entre 0 y 100.")

    return {
        "student_id": int(student_id),
        "session_date": session_date,
        "session_number": session_number,
        "attendance": attendance,
        "grade": grade,
        "topic": topic,
        "observation": observation,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def fetch_students():
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, parent_name, whatsapp, subject, grade_level, institution, created_at
            FROM students
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_student(student_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, parent_name, whatsapp, subject, grade_level, institution, created_at
            FROM students
            WHERE id = ?
            """,
            (student_id,),
        ).fetchone()
    return dict(row) if row else None


def fetch_records(student_id):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, student_id, session_date, session_number, attendance, grade, topic, observation, created_at
            FROM academic_records
            WHERE student_id = ?
            ORDER BY session_date DESC, COALESCE(session_number, 0) DESC, id DESC
            """,
            (student_id,),
        ).fetchall()

    records = []
    for row in rows:
        record = dict(row)
        record["grade_text"] = "-" if record["grade"] is None else f"{record['grade']:.1f}"
        records.append(record)
    return records


def calculate_summary(student_id):
    student = fetch_student(student_id)
    if not student:
        return None

    records = fetch_records(student_id)
    total_sessions = len(records)
    attendance_points = {
        "Asistio": 1,
        "Tarde": 0.75,
        "Excusa": 0.5,
        "No asistio": 0,
    }
    earned_attendance = sum(attendance_points.get(record["attendance"], 0) for record in records)
    attendance_rate = (earned_attendance / total_sessions * 100) if total_sessions else 0

    grades = [record["grade"] for record in records if record["grade"] is not None]
    average_grade = (sum(grades) / len(grades)) if grades else None
    latest_observation = next((record["observation"] for record in records if record["observation"]), "")

    if not records:
        status = "Sin registros"
        recommendation = "Registra la primera sesion para empezar a medir el avance academico."
    elif average_grade is None:
        status = "Sin nota aun"
        recommendation = "Registra una nota numerica para evaluar el rendimiento del estudiante."
    elif average_grade >= 85 and attendance_rate >= 90:
        status = "Excelente"
        recommendation = "Mantener la constancia y proponer retos de profundizacion."
    elif average_grade >= 70 and attendance_rate >= 80:
        status = "Estable"
        recommendation = "Continuar el plan actual y reforzar los temas donde aparezcan dudas."
    elif average_grade >= 60 and attendance_rate >= 70:
        status = "En observacion"
        recommendation = "Reforzar temas basicos, aumentar practica guiada y monitorear de cerca la asistencia."
    else:
        status = "Riesgo academico"
        recommendation = "Programar plan de apoyo inmediato con seguimiento semanal y comunicacion permanente con el acudiente."

    return {
        "student": student,
        "total_sessions": total_sessions,
        "attendance_rate": attendance_rate,
        "attendance_rate_text": f"{attendance_rate:.1f}%",
        "average_grade": average_grade,
        "average_grade_text": "--" if average_grade is None else f"{average_grade:.1f}",
        "latest_observation": latest_observation,
        "status": status,
        "recommendation": recommendation,
    }


def build_whatsapp_message(summary):
    student = summary["student"]
    return (
        f"Hola {student['parent_name']}, te compartimos el estado academico actual de {student['name']} en "
        f"{student['subject']}. Estado: {summary['status']}. Promedio: {summary['average_grade_text']}. "
        f"Asistencia: {summary['attendance_rate_text']}. Sesiones registradas: {summary['total_sessions']}. "
        f"Ultima observacion: {summary['latest_observation'] or 'Sin observaciones registradas.'} "
        f"Recomendacion: {summary['recommendation']}"
    )


def safe_filename(value):
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "estudiante"


def build_excel_export(summary, records):
    student = summary["student"]

    def cell(value, cell_type="String", style=""):
        style_attr = f' ss:StyleID="{style}"' if style else ""
        escaped = html.escape("" if value is None else str(value))
        return f'<Cell{style_attr}><Data ss:Type="{cell_type}">{escaped}</Data></Cell>'

    rows = [
        f"<Row>{cell('Reporte Academico', style='title')}</Row>",
        f"<Row>{cell('Estudiante', style='label')}{cell(student['name'])}</Row>",
        f"<Row>{cell('Acudiente', style='label')}{cell(student['parent_name'])}</Row>",
        f"<Row>{cell('Materia', style='label')}{cell(student['subject'])}</Row>",
        f"<Row>{cell('WhatsApp', style='label')}{cell(student['whatsapp'])}</Row>",
        f"<Row>{cell('Promedio', style='label')}{cell(summary['average_grade_text'])}</Row>",
        f"<Row>{cell('Asistencia', style='label')}{cell(summary['attendance_rate_text'])}</Row>",
        f"<Row>{cell('Estado', style='label')}{cell(summary['status'])}</Row>",
        f"<Row>{cell('Recomendacion', style='label')}{cell(summary['recommendation'])}</Row>",
        "<Row></Row>",
        (
            "<Row>"
            f"{cell('Fecha', style='header')}"
            f"{cell('Sesion', style='header')}"
            f"{cell('Asistencia', style='header')}"
            f"{cell('Nota', style='header')}"
            f"{cell('Tema', style='header')}"
            f"{cell('Observacion', style='header')}"
            "</Row>"
        ),
    ]

    for record in records:
        grade_type = "Number" if record["grade"] is not None else "String"
        grade_value = record["grade"] if record["grade"] is not None else "-"
        rows.append(
            "<Row>"
            f"{cell(record['session_date'])}"
            f"{cell(record['session_number'] or '-')}"
            f"{cell(record['attendance'])}"
            f"{cell(grade_value, grade_type)}"
            f"{cell(record['topic'] or '-')}"
            f"{cell(record['observation'] or '-')}"
            "</Row>"
        )

    workbook = f"""<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
  <Style ss:ID="title"><Font ss:Bold="1" ss:Size="14"/></Style>
  <Style ss:ID="label"><Font ss:Bold="1"/></Style>
  <Style ss:ID="header">
   <Font ss:Bold="1"/>
   <Interior ss:Color="#DDEBF0" ss:Pattern="Solid"/>
  </Style>
 </Styles>
 <Worksheet ss:Name="Seguimiento">
  <Table>
   <Column ss:Width="110"/>
   <Column ss:Width="90"/>
   <Column ss:Width="90"/>
   <Column ss:Width="70"/>
   <Column ss:Width="140"/>
   <Column ss:Width="280"/>
   {''.join(rows)}
  </Table>
 </Worksheet>
</Workbook>"""
    return workbook.encode("utf-8")


def pdf_escape(value):
    sanitized = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return sanitized.encode("latin-1", errors="replace").decode("latin-1")


def build_pdf_export(summary, records):
    student = summary["student"]
    lines = [
        "CINCEL PRO - REPORTE ACADEMICO",
        "",
        f"Estudiante: {student['name']}",
        f"Acudiente: {student['parent_name']}",
        f"Materia: {student['subject']}",
        f"WhatsApp: {student['whatsapp']}",
        f"Promedio: {summary['average_grade_text']}",
        f"Asistencia: {summary['attendance_rate_text']}",
        f"Estado actual: {summary['status']}",
        f"Recomendacion: {summary['recommendation']}",
        "",
        "REGISTROS",
    ]

    if not records:
        lines.append("Sin registros academicos.")
    else:
        for record in records:
            note = record["grade_text"]
            topic = (record["topic"] or "-")[:32]
            observation = (record["observation"] or "-")[:70]
            lines.append(
                f"{record['session_date']} | Sesion {record['session_number'] or '-'} | "
                f"{record['attendance']} | Nota {note} | {topic}"
            )
            lines.append(f"Observacion: {observation}")
            lines.append("")

    page_size = 38
    pages = [lines[index:index + page_size] for index in range(0, len(lines), page_size)] or [[]]
    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    font_obj = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []

    for page_lines in pages:
        text_lines = "\n".join(f"({pdf_escape(line)}) Tj" + ("\nT*" if i != len(page_lines) - 1 else "") for i, line in enumerate(page_lines))
        stream = f"BT\n/F1 11 Tf\n50 790 Td\n14 TL\n{text_lines}\nET"
        stream_bytes = stream.encode("latin-1", errors="replace")
        content_obj = add_object(f"<< /Length {len(stream_bytes)} >>\nstream\n{stream}\nendstream")
        page_obj = add_object(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj} 0 R >>"
        )
        page_ids.append(page_obj)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_obj = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>")
    catalog_obj = add_object(f"<< /Type /Catalog /Pages {pages_obj} 0 R >>")

    pdf_parts = [b"%PDF-1.4\n"]
    offsets = [0]

    for index, content in enumerate(objects, start=1):
        current_offset = sum(len(part) for part in pdf_parts)
        offsets.append(current_offset)
        patched_content = content.replace("/Parent 0 0 R", f"/Parent {pages_obj} 0 R")
        pdf_parts.append(f"{index} 0 obj\n{patched_content}\nendobj\n".encode("latin-1", errors="replace"))

    xref_offset = sum(len(part) for part in pdf_parts)
    pdf_parts.append(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
    pdf_parts.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf_parts.append(f"{offset:010d} 00000 n \n".encode("latin-1"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_obj} 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF"
    )
    pdf_parts.append(trailer.encode("latin-1"))
    return b"".join(pdf_parts)


def send_whatsapp_message(to_number, body):
    account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_WHATSAPP_FROM")

    if not account_sid or not auth_token or not from_number:
        raise RuntimeError(
            "Faltan credenciales de Twilio. Configura TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN y TWILIO_WHATSAPP_FROM para habilitar el envio real."
        )

    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    if not to_number.startswith("whatsapp:"):
        to_number = f"whatsapp:{to_number}"

    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
    payload = parse.urlencode({"From": from_number, "To": to_number, "Body": body}).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
    req = request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("sid")
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"No se pudo enviar el mensaje por WhatsApp: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"No fue posible conectar con Twilio: {exc.reason}") from exc


class CincelHandler(BaseHTTPRequestHandler):
    server_version = "CincelPro/1.0"

    def do_GET(self):
        parsed = parse.urlparse(self.path)

        if parsed.path in STATIC_FILES:
            file_name, content_type = STATIC_FILES[parsed.path]
            file_path = BASE_DIR / file_name
            if not file_path.exists():
                self.send_error(HTTPStatus.NOT_FOUND, "Archivo no encontrado.")
                return
            content = file_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if parsed.path == "/api/students":
            json_response(self, {"students": fetch_students()})
            return

        if parsed.path == "/health":
            json_response(
                self,
                {
                    "status": "ok",
                    "database_path": str(DB_PATH),
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                },
            )
            return

        if parsed.path == "/api/records":
            query = parse.parse_qs(parsed.query)
            student_id = query.get("student_id", [None])[0]
            if not student_id:
                json_response(self, {"error": "Debes indicar el estudiante."}, HTTPStatus.BAD_REQUEST)
                return
            json_response(self, {"records": fetch_records(int(student_id))})
            return

        if parsed.path.startswith("/api/students/") and "/export/" in parsed.path:
            parts = parsed.path.split("/")
            if len(parts) >= 6:
                student_id = int(parts[3])
                export_format = parts[5]
                summary = calculate_summary(student_id)
                if not summary:
                    json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                    return

                records = fetch_records(student_id)
                base_name = safe_filename(summary["student"]["name"])

                if export_format == "excel":
                    body = build_excel_export(summary, records)
                    download_response(
                        self,
                        body,
                        "application/vnd.ms-excel; charset=utf-8",
                        f"seguimiento_{base_name}.xls",
                    )
                    return

                if export_format == "pdf":
                    body = build_pdf_export(summary, records)
                    download_response(
                        self,
                        body,
                        "application/pdf",
                        f"seguimiento_{base_name}.pdf",
                    )
                    return

            json_response(self, {"error": "Formato de exportacion no valido."}, HTTPStatus.BAD_REQUEST)
            return

        if parsed.path.startswith("/api/students/") and parsed.path.endswith("/summary"):
            student_id = parsed.path.split("/")[3]
            summary = calculate_summary(int(student_id))
            if not summary:
                json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            json_response(self, summary)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Ruta no encontrada.")

    def do_POST(self):
        parsed = parse.urlparse(self.path)

        try:
            payload = read_json_body(self)

            if parsed.path == "/api/students":
                student = normalize_student(payload)
                with get_connection() as connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO students (name, parent_name, whatsapp, subject, grade_level, institution, created_at)
                        VALUES (:name, :parent_name, :whatsapp, :subject, :grade_level, :institution, :created_at)
                        """,
                        student,
                    )
                json_response(
                    self,
                    {"message": "Estudiante registrado correctamente.", "student_id": cursor.lastrowid},
                    HTTPStatus.CREATED,
                )
                return

            if parsed.path == "/api/records":
                record = normalize_record(payload)
                if not fetch_student(record["student_id"]):
                    json_response(self, {"error": "El estudiante no existe."}, HTTPStatus.NOT_FOUND)
                    return
                with get_connection() as connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO academic_records (
                            student_id, session_date, session_number, attendance, grade, topic, observation, created_at
                        ) VALUES (
                            :student_id, :session_date, :session_number, :attendance, :grade, :topic, :observation, :created_at
                        )
                        """,
                        record,
                    )
                json_response(
                    self,
                    {"message": "Seguimiento academico registrado.", "record_id": cursor.lastrowid},
                    HTTPStatus.CREATED,
                )
                return

            if parsed.path.startswith("/api/students/") and parsed.path.endswith("/notify"):
                student_id = int(parsed.path.split("/")[3])
                summary = calculate_summary(student_id)
                if not summary:
                    json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
                message_body = build_whatsapp_message(summary)
                sid = send_whatsapp_message(summary["student"]["whatsapp"], message_body)
                json_response(
                    self,
                    {
                        "message": f"Mensaje enviado por WhatsApp al acudiente. SID: {sid}",
                        "sid": sid,
                        "preview": message_body,
                    },
                )
                return

            json_response(self, {"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            json_response(self, {"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except RuntimeError as exc:
            json_response(self, {"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            json_response(self, {"error": f"Error interno del servidor: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self):
        parsed = parse.urlparse(self.path)

        try:
            if parsed.path.startswith("/api/students/"):
                student_id = int(parsed.path.split("/")[3])
                with get_connection() as connection:
                    connection.execute("DELETE FROM academic_records WHERE student_id = ?", (student_id,))
                    result = connection.execute("DELETE FROM students WHERE id = ?", (student_id,))
                if result.rowcount == 0:
                    json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
                json_response(self, {"message": "Estudiante y seguimiento eliminados correctamente."})
                return

            if parsed.path.startswith("/api/records/"):
                record_id = int(parsed.path.split("/")[3])
                with get_connection() as connection:
                    result = connection.execute("DELETE FROM academic_records WHERE id = ?", (record_id,))
                if result.rowcount == 0:
                    json_response(self, {"error": "Registro no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
                json_response(self, {"message": "Registro eliminado correctamente."})
                return

            json_response(self, {"error": "Ruta no encontrada."}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            json_response(self, {"error": f"No se pudo procesar la eliminacion: {exc}"}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format_, *args):
        return


def run():
    init_db()
    port = int(os.environ.get("PORT", "8000"))
    host = os.environ.get("HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), CincelHandler)
    print(f"Cincel Pro escuchando en {host}:{port}")
    if host == "0.0.0.0":
        print(f"Acceso local sugerido: http://127.0.0.1:{port}")
    print(f"Base de datos en: {DB_PATH}")
    server.serve_forever()


if __name__ == "__main__":
    run()
