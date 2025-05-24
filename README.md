# 📝 Bot de Generación y Publicación de Posts en WordPress

Este es un bot de Telegram diseñado para generar y publicar posts en WordPress utilizando modelos de OpenAI, como GPT-3.5 o GPT-4. El bot permite a los usuarios seleccionar el modelo que desean usar, generar contenido basado en un tema proporcionado por el usuario, aplicar sugerencias y finalmente publicar el contenido en un sitio de WordPress.

El proyecto está preparado para implementarse tanto en **Google Cloud Platform (GCP)** como en **entornos locales**. A continuación se detallan las instrucciones para ambos casos.

## 🚀 Funcionalidades

- **Selección del modelo:** El bot permite elegir entre varios modelos de OpenAI (GPT-3.5, GPT-4, etc.).
- **Generación de contenido:** El bot genera automáticamente un título y contenido para un post de blog a partir de un tema proporcionado.
- **Aplicación de sugerencias:** Los usuarios pueden sugerir cambios para mejorar el contenido generado, y el bot actualizará el contenido en base a esas sugerencias.
- **Publicación en WordPress:** Una vez aprobado el contenido, el bot puede publicar el post directamente en WordPress.
- **Interfaz interactiva:** Utiliza botones de Telegram para interactuar con el bot de manera fácil y dinámica.

## ⚙️ Requisitos

Antes de ejecutar el bot, asegúrate de tener los siguientes requisitos:

- **Python 3.7+** instalado en tu máquina.
- **Dependencias** necesarias:
  - Flask
  - Telegram API
  - OpenAI
  - Google Cloud Secret Manager
  - Requests
- Una cuenta de **Google Cloud** y habilitación del **Secret Manager** para almacenar las claves de API.
- Una cuenta de **OpenAI** con claves de API válidas.
- Un **sitio de WordPress** con acceso a la API para la creación de posts.

## 🛠️ Instalación

### 1. Clona este repositorio

```bash
git clone https://github.com/tu_usuario/telegram-bot
cd telegram-bot
```

### 2. Instala las dependencias
Asegúrate de tener pip actualizado y luego instala las dependencias requeridas.

```bash
pip install -r requirements.txt
```

### 3. Configuración de variables de entorno
Debes configurar las siguientes variables de entorno o almacenarlas en Google Cloud Secret Manager:

TELEGRAM_TOKEN: El token de tu bot de Telegram (puedes obtenerlo hablando con BotFather).

WORDPRESS_URL: La URL de tu sitio de WordPress.

WORDPRESS_USER: El nombre de usuario de WordPress para la autenticación API.

WORDPRESS_PASSWORD: La contraseña de WordPress para la autenticación API.

OPENAI_API_KEY: Tu clave de API de OpenAI (puedes obtenerla desde su página oficial).

Alternativamente, puedes cargar estos secretos desde Google Cloud Secret Manager, como se hace en el código, o almacenarlos en un archivo .env (explicado más abajo).

## 🌍 Implementación en Google Cloud Platform (GCP)
Este bot está diseñado para ejecutarse en GCP de manera sencilla. Si deseas implementar el bot en GCP, sigue estos pasos:

### 1. Configuración de Google Cloud
Crea un proyecto en Google Cloud si aún no tienes uno.

Habilita la API de Google Cloud Secret Manager para tu proyecto.

Configura Google Cloud App Engine o Google Cloud Run (según prefieras).

Sube las variables de entorno necesarias (como TELEGRAM_TOKEN, WORDPRESS_URL, OPENAI_API_KEY, etc.) al Secret Manager de Google Cloud, o configúralas en las variables de entorno de la plataforma que uses.

### 2. Desplegar en Google Cloud
#### App Engine (opción recomendada para proyectos simples):

Crea un archivo app.yaml en el directorio raíz de tu proyecto:

yaml
```bash
runtime: python39

entrypoint: gunicorn -b :$PORT app:app

env_variables:
  TELEGRAM_TOKEN: "tu_telegram_token"
  WORDPRESS_URL: "tu_wordpress_url"
  WORDPRESS_USER: "tu_wordpress_user"
  WORDPRESS_PASSWORD: "tu_wordpress_password"
  OPENAI_API_KEY: "tu_openai_api_key"
```

Ejecuta el siguiente comando para desplegar tu aplicación:

```bash
gcloud app deploy
```

#### Google Cloud Run:

Si prefieres usar Cloud Run, sigue estos pasos:

Crea un archivo Dockerfile para empaquetar la aplicación:

dockerfile
```bash
FROM python:3.9-slim

WORKDIR /app

COPY . /app

RUN pip install -r requirements.txt

CMD ["python", "app.py"]
```

Construye y despliega el contenedor:

```bash
gcloud builds submit --tag gcr.io/[PROJECT-ID]/bot-wordpress
gcloud run deploy --image gcr.io/[PROJECT-ID]/bot-wordpress --platform managed
```

## 💻 Ejecución Local
Si prefieres ejecutar el bot de manera local para desarrollo o pruebas, sigue estas instrucciones:

### 1. Configuración del archivo .env
Crea un archivo .env en el directorio raíz de tu proyecto y agrega las variables necesarias. Ejemplo:

env
```bash
TELEGRAM_TOKEN=tu_telegram_token
WORDPRESS_URL=tu_wordpress_url
WORDPRESS_USER=tu_wordpress_user
WORDPRESS_PASSWORD=tu_wordpress_password
OPENAI_API_KEY=tu_openai_api_key
```

### 2. Ejecutar el bot localmente
Para ejecutar el bot de manera local, simplemente ejecuta el siguiente comando:

```bash
python app.py
```

El bot se conectará a Telegram y comenzará a recibir mensajes.

## 🧑‍💻 Uso
### Interacción con el Bot
El bot preguntará al usuario qué modelo de OpenAI desea utilizar (GPT-3.5, GPT-4, etc.).

Luego, el usuario deberá enviar un tema para generar el contenido.

El bot generará un título y contenido para un post de blog en WordPress basado en el tema.

El usuario podrá solicitar cambios, rehacer la propuesta o publicar el contenido en su sitio de WordPress.

Finalmente, si el contenido es aprobado, el post será publicado en el sitio de WordPress y se enviará el enlace al usuario.

### 📝 Estructura del Proyecto
El proyecto está organizado de la siguiente manera:

```bash
bot-wordpress/
│
├── main.py                   # Archivo principal para ejecutar el bot
├── app.yaml                  # Configuración de entorno en Google App Engine
├── cloudbuild.yaml           # Para despliegue automatizado con Google Cloud Build
├── requirements.txt          # Dependencias necesarias para el bot
├── README.md                 # Este archivo
└── .env                      # (Opcional) Archivo con las variables de entorno
```

#### app.py
Este es el archivo principal que ejecuta el bot. Contiene la configuración del webhook y la inicialización del bot de Telegram.

#### content.py
Este archivo contiene las funciones responsables de la generación de contenido usando OpenAI.

#### handlers.py
Contiene la lógica que maneja las interacciones del usuario, como la selección de modelos, la creación de posts y la publicación en WordPress.

#### wordpress.py
Aquí se encuentran las funciones que se encargan de la interacción con la API de WordPress, desde la creación de posts hasta su publicación.

#### utils.py
Este archivo incluye funciones auxiliares, como la animación de carga y la limpieza de contenido.
