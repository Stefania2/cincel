const state = {
    students: [],
    selectedStudentId: null,
    currentSheet: null,
};

const studentForm = document.getElementById("studentForm");
const sheetForm = document.getElementById("sheetForm");
const summaryStudentSelect = document.getElementById("summaryStudentSelect");
const sheetStudentSelect = document.getElementById("sheetStudentSelect");
const studentsTable = document.getElementById("studentsTable");
const studentsEmpty = document.getElementById("studentsEmpty");
const summaryContent = document.getElementById("summaryContent");
const notifyButton = document.getElementById("notifyButton");
const refreshButton = document.getElementById("refreshButton");
const exportExcelButton = document.getElementById("exportExcelButton");
const exportPdfButton = document.getElementById("exportPdfButton");
const saveSheetButton = document.getElementById("saveSheetButton");
const resetSheetButton = document.getElementById("resetSheetButton");
const sheetTableBody = document.getElementById("sheetTableBody");
const activeStudentName = document.getElementById("activeStudentName");
const API_BASE = resolveApiBase();
const TOTAL_ROWS = 20;
const NOTE_COLUMNS = 10;

function resolveApiBase() {
    if (window.CINCEL_API_BASE) {
        return window.CINCEL_API_BASE.replace(/\/$/, "");
    }

    const { protocol, hostname } = window.location;
    if (protocol === "file:" || hostname === "127.0.0.1" || hostname === "localhost") {
        return "";
    }

    if (hostname.endsWith("github.io")) {
        return "https://cincel.onrender.com";
    }

    return "";
}

function showMessage(elementId, text, type = "success") {
    const element = document.getElementById(elementId);
    element.textContent = text;
    element.className = `message show ${type}`;
}

function clearMessage(elementId) {
    const element = document.getElementById(elementId);
    element.textContent = "";
    element.className = "message";
}

function getStatusClass(status) {
    const normalized = (status || "").toLowerCase();
    if (normalized.includes("excelente")) return "status-excelente";
    if (normalized.includes("estable")) return "status-estable";
    if (normalized.includes("observ")) return "status-observacion";
    if (normalized.includes("riesgo")) return "status-riesgo";
    return "status-sin-registros";
}

function currentMonthText() {
    return String(new Date().getMonth() + 1).padStart(2, "0");
}

function currentYearText() {
    return String(new Date().getFullYear());
}

function createBlankRow(rowNumber) {
    const row = {
        row_number: rowNumber,
        class_date: "",
        start_time: "",
        end_time: "",
        total_pages: "",
        partial_pages: "",
        material_code: "",
        material_level: "",
    };

    for (let index = 1; index <= NOTE_COLUMNS; index += 1) {
        row[`note_${index}`] = "";
    }

    return row;
}

function createBlankSheet() {
    return {
        sheet: {
            month: currentMonthText(),
            year: currentYearText(),
            unit_title: "T. Unidad",
            home_title: "T. Casa",
            used_sheets: "",
            monthly_goal: "",
            actual_progress: "",
        },
        rows: Array.from({ length: TOTAL_ROWS }, (_, index) => createBlankRow(index + 1)),
    };
}

async function request(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || "Ocurrio un error inesperado.");
    }
    return data;
}

function renderStudentOptions() {
    const baseOption = state.students.length
        ? ""
        : `<option value="">No hay estudiantes disponibles</option>`;

    const options = state.students
        .map((student) => `<option value="${student.id}">${student.name} - ${student.subject}</option>`)
        .join("");

    summaryStudentSelect.innerHTML = baseOption + options;
    sheetStudentSelect.innerHTML = baseOption + options;

    if (!state.students.length) {
        state.selectedStudentId = null;
        return;
    }

    const validIds = new Set(state.students.map((student) => String(student.id)));
    if (!validIds.has(String(state.selectedStudentId))) {
        state.selectedStudentId = state.students[0].id;
    }

    summaryStudentSelect.value = state.selectedStudentId;
    sheetStudentSelect.value = state.selectedStudentId;
}

function renderStudentsTable() {
    studentsTable.innerHTML = "";
    studentsEmpty.style.display = state.students.length ? "none" : "block";

    state.students.forEach((student) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td><strong>${student.name}</strong><br><span class="subtle">${student.grade_level || "Nivel no especificado"}</span></td>
            <td>${student.parent_name}</td>
            <td>${student.subject}<br><span class="subtle">${student.institution || "Institucion no registrada"}</span></td>
            <td>${student.whatsapp}</td>
            <td class="actions-cell">
                <button class="secondary" type="button" data-open-sheet="${student.id}">Abrir hoja</button>
                <button class="primary" type="button" data-notify="${student.id}">WhatsApp</button>
                <button class="danger" type="button" data-delete-student="${student.id}">Eliminar</button>
            </td>
        `;
        studentsTable.appendChild(row);
    });
}

function renderSummary(summary) {
    if (!summary) {
        summaryContent.innerHTML = "Selecciona un estudiante para abrir su hoja de registro.";
        document.getElementById("kpiAverage").textContent = "--";
        document.getElementById("kpiRows").textContent = "--";
        document.getElementById("kpiA").textContent = "--";
        document.getElementById("kpiSheets").textContent = "--";
        document.getElementById("statusPillHolder").innerHTML = "";
        return;
    }

    document.getElementById("kpiAverage").textContent = summary.average_numeric_text;
    document.getElementById("kpiRows").textContent = String(summary.filled_rows);
    document.getElementById("kpiA").textContent = String(summary.a_count);
    document.getElementById("kpiSheets").textContent = summary.used_sheets_text;
    document.getElementById("statusPillHolder").innerHTML =
        `<span class="status-pill ${getStatusClass(summary.status)}">${summary.status}</span>`;

    summaryContent.innerHTML = `
        <h3>${summary.student.name}</h3>
        <p class="subtle"><strong>Acudiente:</strong> ${summary.student.parent_name} | <strong>Programa:</strong> ${summary.student.subject}</p>
        <p><strong>Hoja activa:</strong> ${summary.sheet.month || "--"}/${summary.sheet.year || "--"}</p>
        <p><strong>Ultima fecha diligenciada:</strong> ${summary.last_record_date || "Sin registros"}</p>
        <p><strong>Meta del mes:</strong> ${summary.sheet.monthly_goal || "Sin definir"} | <strong>Real:</strong> ${summary.sheet.actual_progress || "Sin definir"}</p>
        <p><strong>Recomendacion:</strong> ${summary.recommendation}</p>
    `;
}

function fillSheetMetadata(sheet) {
    document.getElementById("sheetMonth").value = sheet.sheet.month || "";
    document.getElementById("sheetYear").value = sheet.sheet.year || "";
    document.getElementById("unitTitle").value = sheet.sheet.unit_title || "";
    document.getElementById("homeTitle").value = sheet.sheet.home_title || "";
    document.getElementById("usedSheets").value = sheet.sheet.used_sheets || "";
    document.getElementById("monthlyGoal").value = sheet.sheet.monthly_goal || "";
    document.getElementById("actualProgress").value = sheet.sheet.actual_progress || "";
}

function renderSheetRows(rows) {
    sheetTableBody.innerHTML = "";

    rows.forEach((row) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="label-col">${row.row_number}</td>
            <td class="medium-col"><input data-row="${row.row_number}" data-field="class_date" value="${row.class_date || ""}" placeholder="21"></td>
            <td class="small-col"><input data-row="${row.row_number}" data-field="start_time" value="${row.start_time || ""}" placeholder="9:27"></td>
            <td class="small-col"><input data-row="${row.row_number}" data-field="end_time" value="${row.end_time || ""}" placeholder="11:05"></td>
            <td class="small-col"><input data-row="${row.row_number}" data-field="total_pages" value="${row.total_pages || ""}" placeholder="33"></td>
            <td class="small-col"><input data-row="${row.row_number}" data-field="partial_pages" value="${row.partial_pages || ""}" placeholder="F"></td>
            <td class="medium-col align-left"><input data-row="${row.row_number}" data-field="material_code" value="${row.material_code || ""}" placeholder="131"></td>
            <td class="small-col"><input data-row="${row.row_number}" data-field="material_level" value="${row.material_level || ""}" placeholder="F"></td>
            ${Array.from({ length: NOTE_COLUMNS }, (_, index) => {
                const field = `note_${index + 1}`;
                return `<td class="label-col"><input data-row="${row.row_number}" data-field="${field}" value="${row[field] || ""}" placeholder="A"></td>`;
            }).join("")}
        `;
        sheetTableBody.appendChild(tr);
    });
}

function renderSheet(sheet) {
    state.currentSheet = sheet;
    fillSheetMetadata(sheet);
    renderSheetRows(sheet.rows);

    const selectedStudent = state.students.find((student) => student.id === state.selectedStudentId);
    activeStudentName.value = selectedStudent ? selectedStudent.name : "Sin seleccionar";
    const disabled = !selectedStudent;
    Array.from(sheetForm.querySelectorAll("input, button")).forEach((element) => {
        if (element.id === "activeStudentName") return;
        element.disabled = disabled;
    });
}

function collectSheetPayload() {
    const rows = [];

    for (let rowNumber = 1; rowNumber <= TOTAL_ROWS; rowNumber += 1) {
        const row = { row_number: rowNumber };
        const selectors = sheetTableBody.querySelectorAll(`[data-row="${rowNumber}"]`);
        selectors.forEach((input) => {
            row[input.dataset.field] = input.value.trim();
        });
        rows.push(row);
    }

    return {
        sheet: {
            month: document.getElementById("sheetMonth").value.trim(),
            year: document.getElementById("sheetYear").value.trim(),
            unit_title: document.getElementById("unitTitle").value.trim(),
            home_title: document.getElementById("homeTitle").value.trim(),
            used_sheets: document.getElementById("usedSheets").value.trim(),
            monthly_goal: document.getElementById("monthlyGoal").value.trim(),
            actual_progress: document.getElementById("actualProgress").value.trim(),
        },
        rows,
    };
}

async function loadStudents() {
    const data = await request("/api/students");
    state.students = data.students;
    renderStudentOptions();
    renderStudentsTable();
    await loadCurrentStudentData();
}

async function loadCurrentStudentData() {
    if (!state.selectedStudentId) {
        renderSummary(null);
        renderSheet(createBlankSheet());
        activeStudentName.value = "Sin seleccionar";
        return;
    }

    const [summaryData, sheetData] = await Promise.all([
        request(`/api/students/${state.selectedStudentId}/summary`),
        request(`/api/students/${state.selectedStudentId}/register-sheet`),
    ]);

    renderSummary(summaryData);
    renderSheet(sheetData);
}

studentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessage("studentMessage");

    const payload = Object.fromEntries(new FormData(studentForm).entries());
    try {
        const result = await request("/api/students", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        studentForm.reset();
        state.selectedStudentId = Number(result.student_id);
        showMessage("studentMessage", result.message);
        await loadStudents();
    } catch (error) {
        showMessage("studentMessage", error.message, "error");
    }
});

sheetForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessage("sheetMessage");

    if (!state.selectedStudentId) {
        showMessage("sheetMessage", "Primero selecciona un estudiante.", "error");
        return;
    }

    try {
        const result = await request(`/api/students/${state.selectedStudentId}/register-sheet`, {
            method: "POST",
            body: JSON.stringify(collectSheetPayload()),
        });
        showMessage("sheetMessage", result.message);
        await loadCurrentStudentData();
    } catch (error) {
        showMessage("sheetMessage", error.message, "error");
    }
});

summaryStudentSelect.addEventListener("change", async (event) => {
    state.selectedStudentId = Number(event.target.value);
    sheetStudentSelect.value = event.target.value;
    await loadCurrentStudentData();
});

sheetStudentSelect.addEventListener("change", async (event) => {
    state.selectedStudentId = Number(event.target.value);
    summaryStudentSelect.value = event.target.value;
    await loadCurrentStudentData();
});

refreshButton.addEventListener("click", async () => {
    clearMessage("notifyMessage");
    clearMessage("sheetMessage");
    await loadCurrentStudentData();
});

notifyButton.addEventListener("click", async () => {
    if (!state.selectedStudentId) {
        showMessage("notifyMessage", "Primero selecciona un estudiante.", "error");
        return;
    }

    notifyButton.disabled = true;
    clearMessage("notifyMessage");
    try {
        const result = await request(`/api/students/${state.selectedStudentId}/notify`, {
            method: "POST",
        });
        showMessage("notifyMessage", result.message);
    } catch (error) {
        showMessage("notifyMessage", error.message, "error");
    } finally {
        notifyButton.disabled = false;
    }
});

function openExport(format) {
    if (!state.selectedStudentId) {
        showMessage("notifyMessage", "Primero selecciona un estudiante para exportar.", "error");
        return;
    }

    clearMessage("notifyMessage");
    window.open(`${API_BASE}/api/students/${state.selectedStudentId}/export/${format}`, "_blank");
}

exportExcelButton.addEventListener("click", () => openExport("excel"));
exportPdfButton.addEventListener("click", () => openExport("pdf"));

resetSheetButton.addEventListener("click", () => {
    const blank = createBlankSheet();
    if (state.currentSheet?.sheet?.month) blank.sheet.month = state.currentSheet.sheet.month;
    if (state.currentSheet?.sheet?.year) blank.sheet.year = state.currentSheet.sheet.year;
    renderSheet(blank);
    clearMessage("sheetMessage");
});

studentsTable.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;

    if (button.dataset.openSheet) {
        state.selectedStudentId = Number(button.dataset.openSheet);
        summaryStudentSelect.value = button.dataset.openSheet;
        sheetStudentSelect.value = button.dataset.openSheet;
        await loadCurrentStudentData();
        return;
    }

    if (button.dataset.notify) {
        state.selectedStudentId = Number(button.dataset.notify);
        summaryStudentSelect.value = button.dataset.notify;
        sheetStudentSelect.value = button.dataset.notify;
        await loadCurrentStudentData();
        notifyButton.click();
        return;
    }

    if (button.dataset.deleteStudent) {
        const confirmed = window.confirm("Se eliminara el estudiante y toda su hoja de registro. Deseas continuar?");
        if (!confirmed) return;

        try {
            await request(`/api/students/${button.dataset.deleteStudent}`, { method: "DELETE" });
            await loadStudents();
        } catch (error) {
            showMessage("studentMessage", error.message, "error");
        }
    }
});

loadStudents().catch((error) => {
    showMessage("studentMessage", error.message, "error");
});
