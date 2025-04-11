# 📝 Bot de Generación y Publicación de Posts en WordPress

Este es un bot de Telegram diseñado para generar y publicar posts en WordPress utilizando modelos de OpenAI, como GPT-3.5 o GPT-4. El bot permite a los usuarios seleccionar el modelo que desean usar, generar contenido basado en un tema proporcionado por el usuario, aplicar sugerencias y finalmente publicar el contenido en un sitio de WordPress.

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
git clone https://github.com/tu_usuario/bot-wordpress
cd bot-wordpress
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

Alternativamente, puedes cargar estos secretos desde Google Cloud Secret Manager, como se hace en el código, o almacenarlos en un archivo .env.

### 4. Configuración del webhook
Para que el bot funcione correctamente, debes configurar el webhook en el servidor donde lo hospedes. Esto puede hacerse usando el siguiente endpoint:

```bash
https://tu_dominio.com/set_webhook
```
Este endpoint configurará el webhook y comenzará a recibir actualizaciones de Telegram.

## 🧑‍💻 Uso
### Iniciar el Bot
Una vez que hayas configurado todas las variables de entorno y dependencias, puedes ejecutar el bot con el siguiente comando:
```bash
python app.py
```
El bot se conectará a Telegram y comenzará a recibir mensajes.

### Interacción con el Bot
El bot preguntará al usuario qué modelo de OpenAI desea utilizar (GPT-3.5, GPT-4, etc.).

Luego, el usuario deberá enviar un tema para generar el contenido.

El bot generará un título y contenido para un post de blog en WordPress basado en el tema.

El usuario podrá solicitar cambios, rehacer la propuesta o publicar el contenido en su sitio de WordPress.

Finalmente, si el contenido es aprobado, el post será publicado en el sitio de WordPress y se enviará el enlace al usuario.

## 📝 Estructura del Proyecto
El proyecto está organizado de la siguiente manera:

```bash
bot-wordpress/
│
├── app.py                    # Archivo principal para ejecutar el bot
├── content.py                # Funciones de generación de contenido con OpenAI
├── handlers.py               # Lógica de manejo de comandos y respuestas
├── wordpress.py              # Funciones para publicar en WordPress
├── utils.py                  # Funciones utilitarias (limpieza de datos, animaciones, etc.)
├── requirements.txt          # Dependencias necesarias para el bot
├── README.md                 # Este archivo
└── .env                      # (Opcional) Archivo con las variables de entorno
```

### app.py
Este es el archivo principal que ejecuta el bot. Contiene la configuración del webhook y la inicialización del bot de Telegram.

### content.py
Este archivo contiene las funciones responsables de la generación de contenido usando OpenAI.

### handlers.py
Contiene la lógica que maneja las interacciones del usuario, como la selección de modelos, la creación de posts y la publicación en WordPress.

### wordpress.py
Aquí se encuentran las funciones que se encargan de la interacción con la API de WordPress, desde la creación de posts hasta su publicación.

### utils.py
Este archivo incluye funciones auxiliares, como la animación de carga y la limpieza de contenido.

## ⚖️ Licencia
¡Ninguna!

## 🧑‍💻 Contribuciones
Las contribuciones son bienvenidas. Si tienes alguna sugerencia o encuentras algún error, no dudes en abrir un Issue o enviar un Pull Request.

## ¡Gracias por usar el bot! 🚀
