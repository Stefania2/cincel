const state = {
    students: [],
    selectedStudentId: null,
};

const studentForm = document.getElementById("studentForm");
const recordForm = document.getElementById("recordForm");
const summaryStudentSelect = document.getElementById("summaryStudentSelect");
const recordStudentId = document.getElementById("recordStudentId");
const studentsTable = document.getElementById("studentsTable");
const studentsEmpty = document.getElementById("studentsEmpty");
const recordsTable = document.getElementById("recordsTable");
const recordsEmpty = document.getElementById("recordsEmpty");
const summaryContent = document.getElementById("summaryContent");
const notifyButton = document.getElementById("notifyButton");
const refreshButton = document.getElementById("refreshButton");
const exportExcelButton = document.getElementById("exportExcelButton");
const exportPdfButton = document.getElementById("exportPdfButton");

const today = new Date().toISOString().split("T")[0];
document.getElementById("sessionDate").value = today;

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

async function request(path, options = {}) {
    const response = await fetch(path, {
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
    recordStudentId.innerHTML = baseOption + options;

    if (!state.students.length) {
        state.selectedStudentId = null;
        return;
    }

    const validIds = new Set(state.students.map((student) => String(student.id)));
    if (!validIds.has(String(state.selectedStudentId))) {
        state.selectedStudentId = state.students[0].id;
    }

    summaryStudentSelect.value = state.selectedStudentId;
    recordStudentId.value = state.selectedStudentId;
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
                <button class="secondary" type="button" data-select="${student.id}">Ver seguimiento</button>
                <button class="primary" type="button" data-notify="${student.id}">WhatsApp</button>
                <button class="danger" type="button" data-delete-student="${student.id}">Eliminar</button>
            </td>
        `;
        studentsTable.appendChild(row);
    });
}

function renderSummary(summary) {
    if (!summary) {
        summaryContent.innerHTML = "Selecciona un estudiante para ver su seguimiento academico.";
        document.getElementById("kpiAverage").textContent = "--";
        document.getElementById("kpiAttendance").textContent = "--";
        document.getElementById("kpiSessions").textContent = "--";
        document.getElementById("statusPillHolder").innerHTML = "";
        return;
    }

    document.getElementById("kpiAverage").textContent = summary.average_grade_text;
    document.getElementById("kpiAttendance").textContent = summary.attendance_rate_text;
    document.getElementById("kpiSessions").textContent = String(summary.total_sessions);
    document.getElementById("statusPillHolder").innerHTML =
        `<span class="status-pill ${getStatusClass(summary.status)}">${summary.status}</span>`;

    summaryContent.innerHTML = `
        <h3>${summary.student.name}</h3>
        <p class="subtle"><strong>Acudiente:</strong> ${summary.student.parent_name} | <strong>Materia:</strong> ${summary.student.subject}</p>
        <p><strong>Estado actual:</strong> ${summary.status}</p>
        <p><strong>Ultima observacion:</strong> ${summary.latest_observation || "Sin observaciones registradas."}</p>
        <p><strong>Recomendacion:</strong> ${summary.recommendation}</p>
    `;
}

function renderRecords(records) {
    recordsTable.innerHTML = "";
    recordsEmpty.style.display = records.length ? "none" : "block";

    records.forEach((record) => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${record.session_date}</td>
            <td>${record.session_number || "-"}</td>
            <td>${record.attendance}</td>
            <td>${record.grade_text}</td>
            <td>${record.topic || "-"}</td>
            <td>${record.observation || "-"}</td>
            <td class="actions-cell">
                <button class="danger" type="button" data-delete-record="${record.id}">Eliminar</button>
            </td>
        `;
        recordsTable.appendChild(row);
    });
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
        renderRecords([]);
        return;
    }

    const [summaryData, recordsData] = await Promise.all([
        request(`/api/students/${state.selectedStudentId}/summary`),
        request(`/api/records?student_id=${encodeURIComponent(state.selectedStudentId)}`),
    ]);

    renderSummary(summaryData);
    renderRecords(recordsData.records);
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
        showMessage("studentMessage", result.message);
        await loadStudents();
    } catch (error) {
        showMessage("studentMessage", error.message, "error");
    }
});

recordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearMessage("recordMessage");

    const payload = Object.fromEntries(new FormData(recordForm).entries());
    payload.student_id = Number(payload.student_id);
    payload.session_number = payload.session_number ? Number(payload.session_number) : null;
    payload.grade = payload.grade ? Number(payload.grade) : null;

    try {
        const result = await request("/api/records", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        recordForm.reset();
        document.getElementById("sessionDate").value = today;
        recordStudentId.value = state.selectedStudentId || "";
        showMessage("recordMessage", result.message);
        await loadCurrentStudentData();
    } catch (error) {
        showMessage("recordMessage", error.message, "error");
    }
});

summaryStudentSelect.addEventListener("change", async (event) => {
    state.selectedStudentId = Number(event.target.value);
    recordStudentId.value = event.target.value;
    await loadCurrentStudentData();
});

recordStudentId.addEventListener("change", async (event) => {
    state.selectedStudentId = Number(event.target.value);
    summaryStudentSelect.value = event.target.value;
    await loadCurrentStudentData();
});

refreshButton.addEventListener("click", async () => {
    clearMessage("notifyMessage");
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
    window.open(`/api/students/${state.selectedStudentId}/export/${format}`, "_blank");
}

exportExcelButton.addEventListener("click", () => {
    openExport("excel");
});

exportPdfButton.addEventListener("click", () => {
    openExport("pdf");
});

studentsTable.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;

    if (button.dataset.select) {
        state.selectedStudentId = Number(button.dataset.select);
        summaryStudentSelect.value = button.dataset.select;
        recordStudentId.value = button.dataset.select;
        await loadCurrentStudentData();
        return;
    }

    if (button.dataset.notify) {
        state.selectedStudentId = Number(button.dataset.notify);
        summaryStudentSelect.value = button.dataset.notify;
        recordStudentId.value = button.dataset.notify;
        await loadCurrentStudentData();
        notifyButton.click();
        return;
    }

    if (button.dataset.deleteStudent) {
        const confirmed = window.confirm("Se eliminara el estudiante y todo su seguimiento. Deseas continuar?");
        if (!confirmed) return;

        try {
            await request(`/api/students/${button.dataset.deleteStudent}`, { method: "DELETE" });
            await loadStudents();
        } catch (error) {
            showMessage("studentMessage", error.message, "error");
        }
    }
});

recordsTable.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button || !button.dataset.deleteRecord) return;

    const confirmed = window.confirm("Se eliminara este registro academico. Deseas continuar?");
    if (!confirmed) return;

    try {
        await request(`/api/records/${button.dataset.deleteRecord}`, { method: "DELETE" });
        await loadCurrentStudentData();
    } catch (error) {
        showMessage("recordMessage", error.message, "error");
    }
});

loadStudents().catch((error) => {
    showMessage("studentMessage", error.message, "error");
});
