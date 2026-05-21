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
TOTAL_ROWS = 20
NOTE_FIELDS = [f"note_{index}" for index in range(1, 11)]
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/main.html": ("main.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
}


def allowed_origins():
    configured = os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:8000,http://localhost:8000,https://stefania2.github.io",
    )
    return {origin.strip() for origin in configured.split(",") if origin.strip()}


def apply_cors_headers(handler):
    origin = handler.headers.get("Origin")
    if origin and origin in allowed_origins():
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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

            CREATE TABLE IF NOT EXISTS register_sheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL UNIQUE,
                month TEXT,
                year TEXT,
                unit_title TEXT,
                home_title TEXT,
                used_sheets TEXT,
                monthly_goal TEXT,
                actual_progress TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS register_sheet_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_id INTEGER NOT NULL,
                row_number INTEGER NOT NULL,
                class_date TEXT,
                start_time TEXT,
                end_time TEXT,
                total_pages TEXT,
                partial_pages TEXT,
                material_code TEXT,
                material_level TEXT,
                note_1 TEXT,
                note_2 TEXT,
                note_3 TEXT,
                note_4 TEXT,
                note_5 TEXT,
                note_6 TEXT,
                note_7 TEXT,
                note_8 TEXT,
                note_9 TEXT,
                note_10 TEXT,
                FOREIGN KEY(sheet_id) REFERENCES register_sheets(id) ON DELETE CASCADE,
                UNIQUE(sheet_id, row_number)
            );
            """
        )


def json_response(handler, payload, status=HTTPStatus.OK):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    apply_cors_headers(handler)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def download_response(handler, body, content_type, filename):
    handler.send_response(HTTPStatus.OK)
    apply_cors_headers(handler)
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


def clean_text(value):
    return (value or "").strip()


def normalize_student(payload):
    name = clean_text(payload.get("name"))
    parent_name = clean_text(payload.get("parent_name"))
    whatsapp = validate_whatsapp_number(payload.get("whatsapp"))
    subject = clean_text(payload.get("subject"))
    grade_level = clean_text(payload.get("grade_level"))
    institution = clean_text(payload.get("institution"))

    if not name or not parent_name or not subject:
        raise ValueError("Nombre del estudiante, acudiente y programa son obligatorios.")

    return {
        "name": name,
        "parent_name": parent_name,
        "whatsapp": whatsapp,
        "subject": subject,
        "grade_level": grade_level,
        "institution": institution,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }


def default_sheet_metadata():
    now = datetime.now()
    return {
        "month": f"{now.month:02d}",
        "year": str(now.year),
        "unit_title": "T. Unidad",
        "home_title": "T. Casa",
        "used_sheets": "",
        "monthly_goal": "",
        "actual_progress": "",
    }


def blank_row(row_number):
    row = {
        "row_number": row_number,
        "class_date": "",
        "start_time": "",
        "end_time": "",
        "total_pages": "",
        "partial_pages": "",
        "material_code": "",
        "material_level": "",
    }
    for field in NOTE_FIELDS:
        row[field] = ""
    return row


def default_sheet():
    return {
        "sheet": default_sheet_metadata(),
        "rows": [blank_row(index) for index in range(1, TOTAL_ROWS + 1)],
    }


def normalize_sheet_payload(payload):
    sheet_payload = payload.get("sheet") or {}
    rows_payload = payload.get("rows") or []

    sheet = {
        "month": clean_text(sheet_payload.get("month")),
        "year": clean_text(sheet_payload.get("year")),
        "unit_title": clean_text(sheet_payload.get("unit_title")),
        "home_title": clean_text(sheet_payload.get("home_title")),
        "used_sheets": clean_text(sheet_payload.get("used_sheets")),
        "monthly_goal": clean_text(sheet_payload.get("monthly_goal")),
        "actual_progress": clean_text(sheet_payload.get("actual_progress")),
    }

    rows_by_number = {}
    for row_payload in rows_payload:
        try:
            row_number = int(row_payload.get("row_number"))
        except (TypeError, ValueError):
            continue
        if 1 <= row_number <= TOTAL_ROWS:
            rows_by_number[row_number] = row_payload

    rows = []
    for row_number in range(1, TOTAL_ROWS + 1):
        source = rows_by_number.get(row_number, {})
        row = {
            "row_number": row_number,
            "class_date": clean_text(source.get("class_date")),
            "start_time": clean_text(source.get("start_time")),
            "end_time": clean_text(source.get("end_time")),
            "total_pages": clean_text(source.get("total_pages")),
            "partial_pages": clean_text(source.get("partial_pages")),
            "material_code": clean_text(source.get("material_code")),
            "material_level": clean_text(source.get("material_level")),
        }
        for field in NOTE_FIELDS:
            row[field] = clean_text(source.get(field))
        rows.append(row)

    return {"sheet": sheet, "rows": rows}


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


def row_has_content(row):
    keys = [
        "class_date",
        "start_time",
        "end_time",
        "total_pages",
        "partial_pages",
        "material_code",
        "material_level",
        *NOTE_FIELDS,
    ]
    return any(clean_text(row.get(key)) for key in keys)


def fetch_register_sheet(student_id):
    with get_connection() as connection:
        sheet_row = connection.execute(
            """
            SELECT id, student_id, month, year, unit_title, home_title, used_sheets, monthly_goal, actual_progress, updated_at
            FROM register_sheets
            WHERE student_id = ?
            """,
            (student_id,),
        ).fetchone()

        if not sheet_row:
            return default_sheet()

        rows = connection.execute(
            f"""
            SELECT row_number, class_date, start_time, end_time, total_pages, partial_pages, material_code, material_level,
                   {", ".join(NOTE_FIELDS)}
            FROM register_sheet_rows
            WHERE sheet_id = ?
            ORDER BY row_number ASC
            """,
            (sheet_row["id"],),
        ).fetchall()

    existing = {int(row["row_number"]): dict(row) for row in rows}
    ordered_rows = []
    for row_number in range(1, TOTAL_ROWS + 1):
        ordered_rows.append(existing.get(row_number, blank_row(row_number)))

    return {
        "sheet": {
            "month": sheet_row["month"] or "",
            "year": sheet_row["year"] or "",
            "unit_title": sheet_row["unit_title"] or "",
            "home_title": sheet_row["home_title"] or "",
            "used_sheets": sheet_row["used_sheets"] or "",
            "monthly_goal": sheet_row["monthly_goal"] or "",
            "actual_progress": sheet_row["actual_progress"] or "",
        },
        "rows": ordered_rows,
    }


def save_register_sheet(student_id, payload):
    if not fetch_student(student_id):
        raise ValueError("El estudiante no existe.")

    normalized = normalize_sheet_payload(payload)
    timestamp = datetime.now().isoformat(timespec="seconds")

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM register_sheets WHERE student_id = ?",
            (student_id,),
        ).fetchone()

        if existing:
            sheet_id = int(existing["id"])
            connection.execute(
                """
                UPDATE register_sheets
                SET month = :month,
                    year = :year,
                    unit_title = :unit_title,
                    home_title = :home_title,
                    used_sheets = :used_sheets,
                    monthly_goal = :monthly_goal,
                    actual_progress = :actual_progress,
                    updated_at = :updated_at
                WHERE id = :id
                """,
                {
                    **normalized["sheet"],
                    "updated_at": timestamp,
                    "id": sheet_id,
                },
            )
        else:
            cursor = connection.execute(
                """
                INSERT INTO register_sheets (
                    student_id, month, year, unit_title, home_title, used_sheets, monthly_goal, actual_progress, updated_at
                ) VALUES (
                    :student_id, :month, :year, :unit_title, :home_title, :used_sheets, :monthly_goal, :actual_progress, :updated_at
                )
                """,
                {
                    **normalized["sheet"],
                    "student_id": student_id,
                    "updated_at": timestamp,
                },
            )
            sheet_id = cursor.lastrowid

        connection.execute("DELETE FROM register_sheet_rows WHERE sheet_id = ?", (sheet_id,))
        for row in normalized["rows"]:
            connection.execute(
                f"""
                INSERT INTO register_sheet_rows (
                    sheet_id, row_number, class_date, start_time, end_time, total_pages, partial_pages, material_code, material_level,
                    {", ".join(NOTE_FIELDS)}
                ) VALUES (
                    :sheet_id, :row_number, :class_date, :start_time, :end_time, :total_pages, :partial_pages, :material_code, :material_level,
                    {", ".join(f":{field}" for field in NOTE_FIELDS)}
                )
                """,
                {"sheet_id": sheet_id, **row},
            )


def try_parse_number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def calculate_summary(student_id):
    student = fetch_student(student_id)
    if not student:
        return None

    sheet_data = fetch_register_sheet(student_id)
    rows = sheet_data["rows"]
    filled_rows = sum(1 for row in rows if row_has_content(row))
    numeric_notes = []
    a_count = 0
    s_count = 0
    total_pages_sum = 0.0
    last_record_date = ""

    for row in rows:
        if clean_text(row.get("class_date")):
            last_record_date = row["class_date"]

        page_number = try_parse_number(row.get("total_pages"))
        if page_number is not None:
            total_pages_sum += page_number

        for field in NOTE_FIELDS:
            cell = clean_text(row.get(field))
            if not cell:
                continue

            if cell.upper() == "A":
                a_count += 1
                continue

            if cell.upper() == "S":
                s_count += 1
                continue

            number = try_parse_number(cell)
            if number is not None:
                numeric_notes.append(number)

    average_numeric = (sum(numeric_notes) / len(numeric_notes)) if numeric_notes else None
    used_sheets_number = try_parse_number(sheet_data["sheet"].get("used_sheets"))
    used_sheets_text = "--" if not sheet_data["sheet"].get("used_sheets") else sheet_data["sheet"]["used_sheets"]

    if filled_rows == 0:
        status = "Sin registros"
        recommendation = "Empieza a diligenciar la hoja del estudiante para tener seguimiento del mes."
    elif average_numeric is None:
        status = "En seguimiento"
        recommendation = "La hoja tiene actividad registrada; agrega valores numericos si quieres medir promedio."
    elif average_numeric >= 85:
        status = "Excelente"
        recommendation = "Mantener el ritmo y seguir reforzando el trabajo independiente."
    elif average_numeric >= 70:
        status = "Estable"
        recommendation = "Continuar el seguimiento y reforzar los puntos donde aparezcan repeticiones o correcciones."
    elif average_numeric >= 60:
        status = "En observacion"
        recommendation = "Conviene revisar con detalle el material y dedicar mas acompanamiento a los ejercicios clave."
    else:
        status = "Riesgo academico"
        recommendation = "Se recomienda apoyo cercano, revision de rutina diaria y comunicacion continua con el acudiente."

    return {
        "student": student,
        "sheet": sheet_data["sheet"],
        "filled_rows": filled_rows,
        "average_numeric": average_numeric,
        "average_numeric_text": "--" if average_numeric is None else f"{average_numeric:.1f}",
        "a_count": a_count,
        "s_count": s_count,
        "used_sheets_text": used_sheets_text,
        "used_sheets_number": used_sheets_number,
        "total_pages_sum": total_pages_sum,
        "total_pages_sum_text": f"{total_pages_sum:.0f}" if total_pages_sum else "--",
        "last_record_date": last_record_date,
        "status": status,
        "recommendation": recommendation,
    }


def build_whatsapp_message(summary):
    student = summary["student"]
    sheet = summary["sheet"]
    return (
        f"Hola {student['parent_name']}, te compartimos el estado actual de la hoja de registro de {student['name']} "
        f"en {student['subject']}. Mes/Ano: {sheet.get('month') or '--'}/{sheet.get('year') or '--'}. "
        f"Estado: {summary['status']}. Filas diligenciadas: {summary['filled_rows']}. "
        f"Promedio numerico: {summary['average_numeric_text']}. Casillas A: {summary['a_count']}. "
        f"Meta del mes: {sheet.get('monthly_goal') or 'Sin definir'}. Real: {sheet.get('actual_progress') or 'Sin definir'}. "
        f"Recomendacion: {summary['recommendation']}"
    )


def safe_filename(value):
    cleaned = "".join(char if char.isalnum() else "_" for char in value.strip())
    cleaned = cleaned.strip("_")
    return cleaned or "estudiante"


def build_excel_export(summary, sheet_data):
    student = summary["student"]
    sheet = sheet_data["sheet"]
    rows = sheet_data["rows"]

    def cell(value, cell_type="String", style=""):
        style_attr = f' ss:StyleID="{style}"' if style else ""
        escaped = html.escape("" if value is None else str(value))
        return f'<Cell{style_attr}><Data ss:Type="{cell_type}">{escaped}</Data></Cell>'

    lines = [
        f"<Row>{cell('Hoja de Registro', style='title')}</Row>",
        f"<Row>{cell('Estudiante', style='label')}{cell(student['name'])}</Row>",
        f"<Row>{cell('Acudiente', style='label')}{cell(student['parent_name'])}</Row>",
        f"<Row>{cell('Programa', style='label')}{cell(student['subject'])}</Row>",
        f"<Row>{cell('Mes', style='label')}{cell(sheet['month'])}{cell('Ano', style='label')}{cell(sheet['year'])}</Row>",
        f"<Row>{cell('T. Unidad', style='label')}{cell(sheet['unit_title'])}{cell('T. Casa', style='label')}{cell(sheet['home_title'])}</Row>",
        f"<Row>{cell('Hojas utilizadas', style='label')}{cell(sheet['used_sheets'])}{cell('Meta del mes', style='label')}{cell(sheet['monthly_goal'])}{cell('Real', style='label')}{cell(sheet['actual_progress'])}</Row>",
        f"<Row>{cell('Estado', style='label')}{cell(summary['status'])}{cell('Promedio', style='label')}{cell(summary['average_numeric_text'])}</Row>",
        "<Row></Row>",
    ]

    header_cells = [
        "Fila", "Fecha", "Inicio", "Fin", "Tot.", "Parc.", "Material", "Nivel",
        *[str(index) for index in range(1, 11)],
    ]
    lines.append("<Row>" + "".join(cell(header, style="header") for header in header_cells) + "</Row>")

    for row in rows:
        line_cells = [
            row["row_number"],
            row["class_date"],
            row["start_time"],
            row["end_time"],
            row["total_pages"],
            row["partial_pages"],
            row["material_code"],
            row["material_level"],
            *[row[field] for field in NOTE_FIELDS],
        ]
        lines.append("<Row>" + "".join(cell(value) for value in line_cells) + "</Row>")

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
 <Worksheet ss:Name="Registro">
  <Table>
   {''.join(f'<Column ss:Width="{width}"/>' for width in [50, 85, 70, 70, 60, 60, 85, 55, 45, 45, 45, 45, 45, 45, 45, 45, 45, 45])}
   {''.join(lines)}
  </Table>
 </Worksheet>
</Workbook>"""
    return workbook.encode("utf-8")


def pdf_escape(value):
    sanitized = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return sanitized.encode("latin-1", errors="replace").decode("latin-1")


def build_pdf_export(summary, sheet_data):
    student = summary["student"]
    sheet = sheet_data["sheet"]
    rows = sheet_data["rows"]

    lines = [
        "KUMON - HOJA DE REGISTRO",
        "",
        f"Estudiante: {student['name']}",
        f"Acudiente: {student['parent_name']}",
        f"Programa: {student['subject']}",
        f"Mes/Ano: {sheet.get('month') or '--'}/{sheet.get('year') or '--'}",
        f"T. Unidad: {sheet.get('unit_title') or '--'} | T. Casa: {sheet.get('home_title') or '--'}",
        f"Meta del mes: {sheet.get('monthly_goal') or '--'} | Real: {sheet.get('actual_progress') or '--'}",
        f"Estado: {summary['status']} | Promedio: {summary['average_numeric_text']} | Casillas A: {summary['a_count']}",
        "",
        "REGISTRO",
    ]

    for row in rows:
        if not row_has_content(row):
            continue
        line = (
            f"Fila {row['row_number']}: {row['class_date'] or '-'} {row['start_time'] or '-'}-{row['end_time'] or '-'} | "
            f"Tot {row['total_pages'] or '-'} | Parc {row['partial_pages'] or '-'} | Mat {row['material_code'] or '-'} | "
            f"Nivel {row['material_level'] or '-'} | Notas {' '.join((row[field] or '-') for field in NOTE_FIELDS)}"
        )
        lines.append(line[:180])

    if len(lines) == 11:
        lines.append("Sin filas diligenciadas.")

    page_size = 34
    pages = [lines[index:index + page_size] for index in range(0, len(lines), page_size)] or [[]]
    objects = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    font_obj = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids = []

    for page_lines in pages:
        text_lines = "\n".join(
            f"({pdf_escape(line)}) Tj" + ("\nT*" if index != len(page_lines) - 1 else "")
            for index, line in enumerate(page_lines)
        )
        stream = f"BT\n/F1 10 Tf\n36 790 Td\n13 TL\n{text_lines}\nET"
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
    server_version = "CincelPro/2.0"

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        apply_cors_headers(self)
        self.end_headers()

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

        if parsed.path.startswith("/api/students/") and parsed.path.endswith("/register-sheet"):
            student_id = int(parsed.path.split("/")[3])
            if not fetch_student(student_id):
                json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            json_response(self, fetch_register_sheet(student_id))
            return

        if parsed.path.startswith("/api/students/") and parsed.path.endswith("/summary"):
            student_id = int(parsed.path.split("/")[3])
            summary = calculate_summary(student_id)
            if not summary:
                json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                return
            json_response(self, summary)
            return

        if parsed.path.startswith("/api/students/") and "/export/" in parsed.path:
            parts = parsed.path.split("/")
            if len(parts) < 6:
                json_response(self, {"error": "Formato de exportacion no valido."}, HTTPStatus.BAD_REQUEST)
                return

            student_id = int(parts[3])
            export_format = parts[5]
            summary = calculate_summary(student_id)
            if not summary:
                json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                return

            sheet_data = fetch_register_sheet(student_id)
            base_name = safe_filename(summary["student"]["name"])

            if export_format == "excel":
                body = build_excel_export(summary, sheet_data)
                download_response(
                    self,
                    body,
                    "application/vnd.ms-excel; charset=utf-8",
                    f"registro_{base_name}.xls",
                )
                return

            if export_format == "pdf":
                body = build_pdf_export(summary, sheet_data)
                download_response(
                    self,
                    body,
                    "application/pdf",
                    f"registro_{base_name}.pdf",
                )
                return

            json_response(self, {"error": "Formato de exportacion no valido."}, HTTPStatus.BAD_REQUEST)
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

            if parsed.path.startswith("/api/students/") and parsed.path.endswith("/register-sheet"):
                student_id = int(parsed.path.split("/")[3])
                save_register_sheet(student_id, payload)
                json_response(self, {"message": "Hoja de registro guardada correctamente."}, HTTPStatus.CREATED)
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
                    sheet = connection.execute("SELECT id FROM register_sheets WHERE student_id = ?", (student_id,)).fetchone()
                    if sheet:
                        connection.execute("DELETE FROM register_sheet_rows WHERE sheet_id = ?", (sheet["id"],))
                        connection.execute("DELETE FROM register_sheets WHERE id = ?", (sheet["id"],))
                    result = connection.execute("DELETE FROM students WHERE id = ?", (student_id,))
                if result.rowcount == 0:
                    json_response(self, {"error": "Estudiante no encontrado."}, HTTPStatus.NOT_FOUND)
                    return
                json_response(self, {"message": "Estudiante y hoja de registro eliminados correctamente."})
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
