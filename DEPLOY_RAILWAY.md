# Despliegue Gratis en Railway

Este proyecto ya quedo preparado para Railway con:
- `railway.toml` para el arranque.
- `requirements.txt` para que Nixpacks detecte Python.
- `.python-version` para fijar Python 3.13.
- `DATA_DIR` configurable para guardar SQLite en un volumen.

## 1. Sube el proyecto a GitHub
Sube al repositorio estos archivos:
- `main.html`
- `app.js`
- `server.py`
- `railway.toml`
- `requirements.txt`
- `.python-version`
- `.gitignore`

No subas `cincel_academico.db`.

## 2. Crea el proyecto en Railway
1. Entra a [Railway](https://railway.com/).
2. Crea tu cuenta o inicia sesion.
3. Pulsa `New Project`.
4. Elige `Deploy from GitHub repo`.
5. Conecta el repositorio de este proyecto.

## 3. Configura persistencia para que no se borren las notas
1. Dentro del proyecto, agrega un `Volume`.
2. Montalo en la ruta `/data`.
3. En `Variables`, crea:
   `DATA_DIR=/data`

Con eso la base `SQLite` queda en el volumen y no se pierde cuando Railway reinicia o vuelve a desplegar.

## 4. Configura WhatsApp con Twilio
Si quieres envio real por WhatsApp, agrega estas variables:
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_WHATSAPP_FROM`

Ejemplo:
`TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`

## 5. Despliega
Railway tomara automaticamente:
- `railway.toml`
- `PORT`

El proyecto arrancara con:
`python server.py`

## 6. Prueba la app
Cuando termine el deploy, Railway te dara una URL publica, por ejemplo:
`https://tu-app.up.railway.app`

Entra desde cualquier computador usando esa URL.

## 7. Verifica que este sana
Abre:
`/health`

Debe devolver JSON con:
- `status: ok`
- `database_path`
- `timestamp`

## Notas importantes
- El plan gratis de Railway es limitado, pero para este proyecto pequeno suele alcanzar.
- Si no configuras Twilio, la app funciona igual; solo fallara el boton de WhatsApp con un mensaje claro.
