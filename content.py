import openai
from bot.utils import clean_html, clean_response_json

def generate_content_with_model(tema, model="gpt-3.5-turbo"):
    try:
        if "instruct" in model:
            response = openai.Completion.create(
                model=model,
                prompt=f"Genera un título y contenido en JSON para: {tema}",
                max_tokens=700,
                temperature=0.7
            )
            content = response.choices[0].text.strip()
        else:
            response = openai.ChatCompletion.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Eres experto en generación de contenido."},
                    {"role": "user", "content": f"Genera un artículo sobre: {tema} en JSON con 'title' y 'content'"}
                ]
            )
            content = response['choices'][0]['message']['content'].strip()

        content = clean_response_json(content)
        post_data = json.loads(content)
        title = post_data.get("title", "Título no encontrado")
        content = clean_html(post_data.get("content", ""))
        return title, content
    except Exception as e:
        return "Error generando título", "No se pudo generar contenido."

def apply_suggestions(old_content, suggestions, model="gpt-3.5-turbo"):
    # Similar a generate_content_with_model pero incluye sugerencias del usuario
    pass
