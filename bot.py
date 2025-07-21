from keep_alive import keep_alive
import os
import sqlite3
import logging
import re
from datetime import datetime
from dotenv import load_dotenv

import google.generativeai as genai

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# Carrega variáveis de ambiente do arquivo .env
load_dotenv()

# --- Configuração das Chaves e Logging ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Validação inicial das chaves
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    print("\n🚨 ERRO CRÍTICO: Chaves de API não encontradas no arquivo .env. Verifique o arquivo e tente novamente.")
    exit()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuração da API do Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# Constantes
DB_FILE = "trader_bot.db"
MAX_INTERACTIONS_PER_DAY = 10
COMMUNITY_LINK = os.getenv("COMMUNITY_LINK", "https://t.me/unitytradersoficialsmc") # Adicione seu link no .env
MIN_ANSWER_LENGTH = 15 # Mínimo de caracteres para uma resposta ser considerada completa

# Estados da conversa
(
    ASKING_LANGUAGE,
    ASKING_PERSONA,
    ASKING_PROFILE_NAME,
    ASKING_PROFILE_AGE,
    ASKING_PROFILE_EXPERIENCE,
    ASKING_PROFILE_SATISFACTION,
    ASKING_PROFILE_REASON,
    ASKING_PROFILE_SOURCE,
    ASKING_PROFILE_GOAL,
    ASKING_PROFILE_FEAR,
    ASKING_PRETRADE,
    AWAITING_PRETRADE_CONFIRMATION,
    AWAITING_FOCUS_CHOICE,
    ASKING_POSTRADE_DETAILS,
    ASKING_POSTRADE_EMOTION,
    ASKING_POSTRADE_ACTIONS,
    ASKING_EOD,
    ASKING_DORMIR,
    AWAITING_REDEFINE_CONFIRMATION,
) = range(19)

# --- Gerenciamento de Idiomas (i18n) ---
PERSONAS = {
    'pt': {'male': 'Dr. Fernando Macedo', 'female': 'Dra. Angelica Oliveira'},
    'en': {'male': 'Dr. Devon Taylor', 'female': 'Dr. Jenny Williams'},
    'es': {'male': 'Dr. Alejandro Pérez', 'female': 'Dra. Emma Jiménez'}
}

LANGUAGES = {
    'pt': {
        'choose_language': "Por favor, escolha seu idioma. | Please choose your language. | Por favor, elija su idioma.",
        'welcome_new': "Bem-vindo à sua arena de alta performance. Serei seu mentor da Unity Alta Performance e estarei ao seu lado para forjar a mentalidade que separa os 95% que desistem dos 5% que alcançam a consistência.\n\nPara isso, preciso do seu compromisso total. Nossa jornada começa com uma sessão de diagnóstico profundo. Quando estiver pronto para se comprometer com a sua evolução, use o comando /perfil.",
        'welcome_back': "Bem-vindo de volta, {name}. Comigo, seu mentor {mentor_name}, seu foco continua sendo '{goal}' e nosso trabalho é dominar sua tendência de '{fear}'.\n\nComandos disponíveis:\n🔹 /pretrade\n🔹 /postrade\n🔹 /eod\n🔹 /dormir\n🔹 /perfil\n🔹 /redefinir",
        'profile_needed': "Para usar este comando, primeiro precisamos definir sua jornada. Por favor, configure seu perfil com o comando /perfil.",
        'redefine_confirm': "Você tem certeza que deseja apagar seu perfil e recomeçar sua jornada? Todo o seu progresso de perfil será perdido. Responda 'sim' para confirmar.",
        'redefine_success': "Seu perfil foi redefinido. Use /start para começar uma nova jornada.",
        'redefine_cancel': "Ação cancelada. Seu perfil está seguro.",
        'limit_reached': "Você atingiu seu limite de interações por hoje. A consistência também se constrói no descanso. Nos falamos amanhã.",
        'cancel_conversation': "Ok, conversa cancelada. Estou aqui quando precisar.",
        'unknown_command': "Desculpe, não entendi esse comando. Tente /start para ver as opções disponíveis.",
        'next_step_prompt': "\n\nEstou pronto para o próximo passo. Comandos disponíveis: /pretrade, /postrade, /eod, /dormir.",
        'elaboration_needed': "Para uma análise profunda e eficaz, preciso de mais detalhes. Por favor, elabore sua resposta.",
        'profile_q_persona': "Para começar, com qual de nossos mentores de alta performance você gostaria de trabalhar?",
        'profile_q_name': "Ótima escolha. Para tornar nossa mentoria o mais pessoal possível, como você gostaria de ser chamado?",
        'profile_q_age': "Prazer, {name}. Quantos anos você tem?",
        'profile_q_experience': "Entendido. Há quanto tempo você opera no mercado financeiro?",
        'profile_q_satisfaction': "E sobre seus resultados atuais, você está satisfeito com sua performance ou sente que poderia ir muito além?",
        'profile_q_reason': "Entendi. Essa é uma percepção importante. Na sua opinião, por que você acredita que ainda não alcançou a consistência? Seja o mais honesto possível.",
        'profile_q_source': "Obrigado pela honestidade. Para nos ajudar a melhorar, como você descobriu este mentor? (Ex: Amigo, Grupo no Telegram, YouTube, etc.)",
        'profile_q_goal': "Isso é um ótimo ponto de partida. Agora, qual é o seu maior objetivo como trader? O que te move todos os dias? (Ex: Viver do mercado, ter liberdade financeira, provar que sou capaz)",
        'profile_q_fear': "Entendido. Agora, a parte mais importante: qual é a sua maior fraqueza ou medo? O que mais te sabota? (Ex: Ansiedade que me faz sair cedo, ganância após uma vitória, medo de arriscar)",
        'profile_complete': "Perfil configurado, {name}. Nosso contrato está selado: vamos trabalhar para alcançar '{goal}' enquanto dominamos sua tendência de '{fear}'.\n\nA jornada de um trader de elite é solitária, mas não precisa ser. Junte-se à nossa comunidade de operadores focados em performance para discutir estratégias e evoluir em conjunto: {community_link}\n\nAgora, vamos ao trabalho. Comece com /pretrade.",
        'pretrade_q_plan': "Seu maior desafio é '{fear}'. Defina seu plano de trading para hoje, detalhando como você vai se blindar contra isso.",
        'pretrade_analyzing': "Analisando seu plano...",
        'pretrade_confirm_diagnosis': "Este diagnóstico inicial faz sentido para você? Responda 'sim' para escolher o ponto que deseja trabalhar hoje, ou /cancel para concluir.",
        'pretrade_no_points': "Não consegui identificar os pontos de melhoria no diagnóstico. Vamos focar no plano geral por hoje. Um ótimo dia de operações.",
        'pretrade_choose_focus': "Excelente. Abaixo estão os pontos identificados. Digite o número do **único ponto** que você quer focar hoje (ex: 1).\n\n{points}",
        'pretrade_invalid_choice': "Por favor, escolha **apenas 1** ponto. (Ex: 1)",
        'pretrade_invalid_number': "O número {number} não é uma opção válida. Tente novamente.",
        'pretrade_action_plan_generating': "Ótima escolha. Preparando seu plano de ação comportamental focado...",
        'pretrade_eod_instruction': "Foco total neste plano de ação. Volte no final do seu dia de operações e me chame com o comando /eod. Um excelente dia!",
        'postrade_q_details': "Operação finalizada. Descreva o gatilho para entrar na operação e como foi a saída.",
        'postrade_q_emotion': "Entendido. Qual foi a emoção predominante que você sentiu durante esta operação? (Ex: Confiança, Ansiedade, Medo, Euforia, Tédio)",
        'postrade_q_actions': "Ok. E durante a operação, você realizou alguma ação que não estava no seu plano original? (Ex: Movi o stop, zerei antes do alvo, aumentei a mão)",
        'postrade_analyzing': "Analisando a execução, emoções e ações...",
        'eod_q_generic': "Fim do dia. Hoje, suas ações foram guiadas mais pelo seu objetivo de '{goal}' ou pela sua dificuldade com '{fear}'? Descreva a situação que mais testou sua disciplina.",
        'eod_q_plan': "Seu plano para hoje era:\n*\"{plan}\"*\n\nConsiderando seu objetivo de '{goal}' e sua luta contra '{fear}', como foi sua aderência a este plano?",
        'eod_analyzing': "Analisando seu dia...",
        'dormir_q': "Qual o último pensamento ou preocupação sobre o mercado que está na sua mente? Vamos transformá-lo em força para o descanso.",
        'dormir_processing': "Preparando suas afirmações...",
        'ai_system_prompt_male': "Você é o {mentor_name}, um mentor comportamental de elite para traders, especialista nos princípios do Estado de Flow de Mihaly Csikszentmihalyi. Seja conciso e direto. Sua análise deve ser profunda, mas suas respostas, curtas e acionáveis. Use os dados do perfil do trader como contexto para sua análise, mas evite repeti-los na sua resposta.",
        'ai_system_prompt_female': "Você é a {mentor_name}, uma mentora comportamental de elite para traders, especialista em técnicas de Foco Executivo e Ancoragem no Presente. Seja concisa e direta. Sua análise deve ser profunda, mas suas respostas, curtas e acionáveis. Use os dados do perfil do trader como contexto para sua análise, mas evite repeti-los na sua resposta.",
        'ai_task_diagnose': "Com base nos dados, faça um diagnóstico comportamental preciso em 1-2 frases. Depois, liste de 2 a 3 pontos de melhoria claros (Ex: 1. ... 2. ...). Finalize com 1 pergunta poderosa que force a autoconsciência.",
        'ai_task_improve': "O trader escolheu focar no seguinte ponto-chave. Crie um 'Plano de Ação Comportamental' focado EXCLUSIVAMENTE neste único ponto. Seja extremamente direto.\n1. Sugira uma técnica específica e baseada em evidências (em 1-2 frases).\n2. Finalize com uma frase de alinhamento (em 1 frase).",
        'ai_task_affirmation': "O trader compartilhou seu último pensamento antes de dormir. Com base no seu perfil (objetivo e medo) e neste pensamento, gere 3 afirmações curtas e poderosas para a noite. As afirmações devem quebrar crenças limitantes e fortalecer a confiança para o próximo dia. Seja inspirador e direto.",
    },
    'en': {
        'choose_language': "Please choose your language.",
        'welcome_new': "Welcome to your high-performance arena. I will be your mentor from Unity Alta Performance, and I will be by your side, in the trenches, to forge the mindset that separates the 95% who give up from the 5% who achieve consistency.\n\nFor this, I need your total commitment. Our journey begins with a deep diagnostic session. When you are ready to commit to your evolution, use the /profile command.",
        'welcome_back': "Welcome back, {name}. With me, your mentor {mentor_name}, your focus remains on '{goal}' and our job is to master your tendency for '{fear}'.\n\nAvailable commands:\n🔹 /pretrade\n🔹 /postrade\n🔹 /eod\n🔹 /dormir\n🔹 /profile\n🔹 /reset",
        'profile_needed': "To use this command, we first need to define your journey. Please set up your profile with the /profile command.",
        'redefine_confirm': "Are you sure you want to delete your profile and restart your journey? All your profile progress will be lost. Reply 'yes' to confirm.",
        'redefine_success': "Your profile has been reset. Use /start to begin a new journey.",
        'redefine_cancel': "Action cancelled. Your profile is safe.",
        'limit_reached': "You have reached your daily interaction limit. Consistency is also built on rest. We'll talk tomorrow.",
        'cancel_conversation': "Ok, conversation cancelled. I'm here when you need me.",
        'unknown_command': "Sorry, I didn't understand that command. Try /start to see the available options.",
        'next_step_prompt': "\n\nI'm ready for the next step. Available commands: /pretrade, /postrade, /eod, /dormir.",
        'elaboration_needed': "For a deep and effective analysis, I need more details. Please elaborate on your answer.",
        'profile_q_persona': "To begin, which of our high-performance mentors would you like to work with?",
        'profile_q_name': "Great choice. To make our mentoring as personal as possible, what would you like to be called?",
        'profile_q_age': "Nice to meet you, {name}. How old are you?",
        'profile_q_experience': "Understood. How long have you been trading in the financial market?",
        'profile_q_satisfaction': "And regarding your current results, are you satisfied with your performance, or do you feel you could go much further?",
        'profile_q_reason': "I see. That's an important insight. In your opinion, why do you believe you haven't achieved consistency yet? Be as honest as possible.",
        'profile_q_source': "Thank you for your honesty. To help us improve, how did you find out about this mentor? (e.g., Friend, Telegram Group, YouTube, etc.)",
        'profile_q_goal': "That's a great starting point. Now, what is your biggest goal as a trader? What drives you every day? (e.g., Living off the market, financial freedom, proving I can do it)",
        'profile_q_fear': "Understood. Now, the most important part: what is your biggest weakness or fear? What sabotages you the most? (e.g., Anxiety that makes me exit early, greed after a win, fear of taking risks)",
        'profile_complete': "Profile set up, {name}. Our contract is sealed: we will work to achieve '{goal}' while mastering your tendency for '{fear}'.\n\nThe journey of an elite trader is lonely, but it doesn't have to be. Join our community of performance-focused traders to discuss strategies and evolve together: {community_link}\n\nNow, let's get to work. Start with /pretrade.",
        'pretrade_q_plan': "Your biggest challenge is '{fear}'. Define your battle plan for today, detailing how you will shield yourself from it.",
        'pretrade_analyzing': "Analyzing your plan...",
        'pretrade_confirm_diagnosis': "Does this initial diagnosis make sense to you? Reply 'yes' to choose the point you want to work on today, or /cancel to finish.",
        'pretrade_no_points': "I couldn't identify improvement points in the diagnosis. Let's focus on the general plan for today. Have a great trading day.",
        'pretrade_choose_focus': "Excellent. Below are the identified points. Enter the number of the **single point** you want to focus on today (e.g., 1).\n\n{points}",
        'pretrade_invalid_choice': "Please choose **only 1** point. (e.g., 1)",
        'pretrade_invalid_number': "The number {number} is not a valid option. Please try again.",
        'pretrade_action_plan_generating': "Great choice. Preparing your focused behavioral action plan...",
        'pretrade_eod_instruction': "Full focus on this action plan. Come back at the end of your trading day and call me with the /eod command. Have an excellent day!",
        'postrade_q_details': "Trade finished. Describe the trigger for entering the trade and how the exit was.",
        'postrade_q_emotion': "Understood. What was the predominant emotion you felt during this trade? (e.g., Confidence, Anxiety, Fear, Euphoria, Boredom)",
        'postrade_q_actions': "Ok. And during the trade, did you take any action that was not in your original plan? (e.g., Moved the stop, closed before the target, increased position size)",
        'postrade_analyzing': "Analyzing execution, emotions, and actions...",
        'eod_q_generic': "End of day. Today, were your actions guided more by your goal of '{goal}' or by your difficulty with '{fear}'? Describe the situation that most tested your discipline.",
        'eod_q_plan': "Your plan for today was:\n*\"{plan}\"*\n\nConsidering your goal of '{goal}' and your struggle with '{fear}', how was your adherence to this plan?",
        'eod_analyzing': "Analyzing your day...",
        'dormir_q': "What is the last market-related thought or worry on your mind? Let’s turn it into strength for your rest.",
        'dormir_processing': "Preparing your affirmations...",
        'ai_system_prompt_male': "You are {mentor_name}, an elite behavioral mentor for high-performance traders, an expert in the principles of Flow State by Mihaly Csikszentmihalyi. Be concise and direct. Your analysis must be deep, but your answers short and actionable. Use the trader's profile data as context for your analysis, but avoid repeating it in your response.",
        'ai_system_prompt_female': "You are {mentor_name}, an elite behavioral mentor for high-performance traders, an expert in Executive Focus and Present Moment Anchoring techniques. Be concise and direct. Your analysis must be deep, but your answers short and actionable. Use the trader's profile data as context for your analysis, but avoid repeating it in your response.",
        'ai_task_diagnose': "Based on the data, provide a precise behavioral diagnosis in 1-2 short sentences. Then, list 2-3 clear improvement points (e.g., 1. ... 2. ...). End with 1 powerful question that forces self-awareness.",
        'ai_task_improve': "The trader has chosen to focus on the following key point. Create a 'Behavioral Action Plan' focused EXCLUSIVELY on this single point. Be extremely direct.\n1. Suggest a specific, evidence-based technique (in 1-2 sentences).\n2. Conclude with an alignment statement (in 1 sentence).",
        'ai_task_affirmation': "The trader has shared their last thought before sleeping. Based on their profile (goal and fear) and this thought, generate 3 short, powerful affirmations for the night. The affirmations should break limiting beliefs and build confidence for the next day. Be inspiring and direct.",
    },
    'es': {
        'choose_language': "Por favor, elija su idioma.",
        'welcome_new': "Bienvenido a tu arena de alto rendimiento. Seré tu mentor de Unity Alta Performance, y estaré a tu lado, en las trincheras, para forjar la mentalidad que separa al 95% que abandona del 5% que alcanza la consistencia.\n\nPara ello, necesito tu compromiso total. Nuestro viaje comienza con una sesión de diagnóstico profundo. Cuando estés listo para comprometerte con tu evolución, usa el comando /perfil.",
        'welcome_back': "Bienvenido de nuevo, {name}. Conmigo, tu mentor {mentor_name}, tu enfoque sigue siendo '{goal}' y nuestro trabajo es dominar tu tendencia a '{fear}'.\n\nComandos disponibles:\n🔹 /pretrade\n🔹 /postrade\n🔹 /eod\n🔹 /dormir\n🔹 /perfil\n🔹 /reiniciar",
        'profile_needed': "Para usar este comando, primero debemos definir tu viaje. Por favor, configura tu perfil con el comando /perfil.",
        'redefine_confirm': "¿Estás seguro de que quieres borrar tu perfil y reiniciar tu viaje? Todo el progreso de tu perfil se perderá. Responde 'sí' para confirmar.",
        'redefine_success': "Tu perfil ha sido reiniciado. Usa /start para comenzar un nuevo viaje.",
        'redefine_cancel': "Acción cancelada. Tu perfil está a salvo.",
        'limit_reached': "Has alcanzado tu límite diario de interacciones. La consistencia también se construye con el descanso. Hablamos mañana.",
        'cancel_conversation': "Ok, conversación cancelada. Estoy aquí cuando me necesites.",
        'unknown_command': "Lo siento, no entendí ese comando. Prueba /start para ver las opciones disponibles.",
        'next_step_prompt': "\n\nEstoy listo para el siguiente paso. Comandos disponibles: /pretrade, /postrade, /eod, /dormir.",
        'elaboration_needed': "Para un análisis profundo y eficaz, necesito más detalles. Por favor, elabora tu respuesta.",
        'profile_q_persona': "Para empezar, ¿con cuál de nuestros mentores de alto rendimiento te gustaría trabajar?",
        'profile_q_name': "Excelente elección. Para que nuestra mentoría sea lo más personal posible, ¿cómo te gustaría que te llamara?",
        'profile_q_age': "Encantado de conocerte, {name}. ¿Cuántos años tienes?",
        'profile_q_experience': "Entendido. ¿Cuánto tiempo llevas operando en el mercado financiero?",
        'profile_q_satisfaction': "Y sobre tus resultados actuales, ¿estás satisfecho con tu rendimiento o sientes que podrías llegar mucho más lejos?",
        'profile_q_reason': "Entiendo. Es una percepción importante. En tu opinión, ¿por qué crees que aún no has alcanzado la consistencia? Sé lo más honesto posible.",
        'profile_q_source': "Gracias por tu honestidad. Para ayudarnos a mejorar, ¿cómo descubriste a este mentor? (Ej: Amigo, Grupo de Telegram, YouTube, etc.)",
        'profile_q_goal': "Ese es un gran punto de partida. Ahora, ¿cuál es tu mayor objetivo como trader? ¿Qué te mueve cada día? (Ej: Vivir del mercado, tener libertad financiera, demostrar que soy capaz)",
        'profile_q_fear': "Entendido. Ahora, la parte más importante: ¿cuál es tu mayor debilidad o miedo? ¿Qué es lo que más te sabotea? (Ej: Ansiedad que me hace salir pronto, codicia después de una victoria, miedo a arriesgar)",
        'profile_complete': "Perfil configurado, {name}. Nuestro contrato está sellado: trabajaremos para alcanzar '{goal}' mientras dominamos tu tendencia a '{fear}'.\n\nEl viaje de un trader de élite es solitario, pero no tiene por qué serlo. Únete a nuestra comunidad de operadores centrados en el rendimiento para discutir estrategias y evolucionar juntos: {community_link}\n\nAhora, manos a la obra. Comienza con /pretrade.",
        'pretrade_q_plan': "Tu mayor desafío es '{fear}'. Define tu plan de batalla para hoy, detallando cómo te protegerás de él.",
        'pretrade_analyzing': "Analizando tu plan...",
        'pretrade_confirm_diagnosis': "¿Este diagnóstico inicial tiene sentido para ti? Responde 'sí' para elegir los puntos en los que quieres trabajar hoy, o /cancel para terminar.",
        'pretrade_no_points': "No pude identificar puntos de mejora en el diagnóstico. Centrémonos en el plan general por hoy. Que tengas un gran día de trading.",
        'pretrade_choose_focus': "Excelente. A continuación se muestran los puntos identificados. Escribe el número del **único punto** en el que quieres centrarte hoy (ej: 1).\n\n{points}",
        'pretrade_invalid_choice': "Por favor, elige **solo 1** punto. (Ej: 1)",
        'pretrade_invalid_number': "El número {number} no es una opción válida. Inténtalo de nuevo.",
        'pretrade_action_plan_generating': "Gran elección. Preparando tu plan de acción conductual enfocado...",
        'pretrade_eod_instruction': "Enfoque total en este plan de acción. Vuelve al final de tu día de operaciones y llámame con el comando /eod. ¡Que tengas un excelente día!",
        'postrade_q_details': "Operación finalizada. Describe el detonante para entrar en la operación y cómo fue la salida.",
        'postrade_q_emotion': "Entendido. ¿Cuál fue la emoción predominante que sentiste durante esta operación? (Ej: Confianza, Ansiedad, Miedo, Euforia, Aburrimiento)",
        'postrade_q_actions': "Ok. Y durante la operación, ¿realizaste alguna acción que no estuviera en tu plan original? (Ej: Moví el stop, cerré antes del objetivo, aumenté la posición)",
        'postrade_analyzing': "Analizando ejecución, emociones y acciones...",
        'eod_q_generic': "Fin del día. Hoy, ¿tus acciones fueron guiadas más por tu objetivo de '{goal}' o por tu dificultad con '{fear}'? Describe la situación que más puso a prueba tu disciplina.",
        'eod_q_plan': "Tu plan para hoy era:\n*\"{plan}\"*\n\nConsiderando tu objetivo de '{goal}' y tu lucha contra '{fear}', ¿cómo fue tu adherencia a este plan?",
        'eod_analyzing': "Analizando tu día...",
        'dormir_q': "¿Cuál es el último pensamiento o preocupación sobre el mercado que tienes en mente? Vamos a convertirlo en fuerza para tu descanso.",
        'dormir_processing': "Preparando tus afirmaciones...",
        'ai_system_prompt_male': "Eres {mentor_name}, un mentor de comportamiento de élite para traders de alto rendimiento, experto en los principios del Estado de Flujo de Mihaly Csikszentmihalyi. Sé conciso y directo. Tu análisis debe ser profundo, pero tus respuestas cortas y accionables. Usa los datos del perfil del trader como contexto para tu análisis, pero evita repetirlos en tu respuesta.",
        'ai_system_prompt_female': "Eres {mentor_name}, una mentora de comportamiento de élite para traders de alto rendimiento, experta en técnicas de Enfoque Ejecutivo y Anclaje en el Presente. Sé conciso y directo. Tu análisis debe ser profundo, pero tus respuestas cortas y accionables. Usa los datos del perfil del trader como contexto para tu análisis, pero evita repetirlos en tu respuesta.",
        'ai_task_diagnose': "Basado en los datos proporcionados, realiza un diagnóstico conductual preciso en 1-2 frases cortas. Luego, lista 2-3 puntos de mejora claros (Ej: 1. ... 2. ...). Finaliza con 1 pregunta final poderosa que fuerce la autoconciencia.",
        'ai_task_improve': "El trader ha elegido centrarse en el siguiente punto clave. Crea un 'Plan de Acción Conductual' enfocado EXCLUSIVAMENTE en este único punto. Sé extremadamente directo.\n1. Sugiere una técnica específica y basada en evidencia (en 1-2 frases).\n2. Concluye con una frase de alineación (en 1 frase).",
        'ai_task_affirmation': "El trader ha compartido su último pensamiento antes de dormir. Basado en su perfil (objetivo y miedo) y en este pensamiento, genera 3 afirmaciones cortas y poderosas para la noche. Las afirmaciones deben romper creencias limitantes y fortalecer la confianza para el día siguiente. Sé inspirador y directo.",
    }
}

def get_text(key, lang='pt', **kwargs):
    """Busca um texto traduzido."""
    return LANGUAGES.get(lang, LANGUAGES['pt']).get(key, key).format(**kwargs)

# --- Funções do Banco de Dados (SQLite) ---

def init_db():
    """Inicializa o banco de dados e cria as tabelas se não existirem."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        language TEXT DEFAULT 'pt',
        last_update TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        age INTEGER,
        experience TEXT,
        satisfaction TEXT,
        source TEXT,
        goal TEXT,
        fear TEXT,
        persona TEXT,
        inconsistency_reason TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS interactions (
        interaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        command TEXT,
        user_message TEXT,
        ai_response TEXT,
        timestamp TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_plans (
        user_id INTEGER,
        plan_date TEXT,
        plan_text TEXT,
        PRIMARY KEY (user_id, plan_date)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        trade_description TEXT,
        emotion TEXT,
        unplanned_actions TEXT,
        ai_analysis TEXT,
        timestamp TEXT,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    """)
    conn.commit()
    conn.close()

def set_user_language(user_id: int, lang_code: str):
    """Define o idioma do usuário."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang_code, user_id))
    conn.commit()
    conn.close()
    logger.info(f"Idioma do usuário {user_id} definido para {lang_code}.")

def get_user_language(user_id: int) -> str:
    """Busca o idioma do usuário."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 'pt'

def save_user_profile(user_id: int, profile_data: dict):
    """Salva ou atualiza o perfil de um usuário."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO user_profiles (user_id, name, age, experience, satisfaction, source, goal, fear, persona, inconsistency_reason) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET 
        name=excluded.name, age=excluded.age, experience=excluded.experience, 
        satisfaction=excluded.satisfaction, source=excluded.source, goal=excluded.goal, fear=excluded.fear, persona=excluded.persona,
        inconsistency_reason=excluded.inconsistency_reason
    """, (
        user_id,
        profile_data.get('name'),
        profile_data.get('age'),
        profile_data.get('experience'),
        profile_data.get('satisfaction'),
        profile_data.get('source'),
        profile_data.get('goal'),
        profile_data.get('fear'),
        profile_data.get('persona'),
        profile_data.get('inconsistency_reason')
    ))
    conn.commit()
    conn.close()
    logger.info(f"Perfil salvo para o usuário {user_id}.")

def get_user_profile(user_id: int) -> dict | None:
    """Busca o perfil de um usuário."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT name, age, experience, satisfaction, source, goal, fear, persona, inconsistency_reason FROM user_profiles WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        return {
            'name': result[0], 'age': result[1], 'experience': result[2],
            'satisfaction': result[3], 'source': result[4], 'goal': result[5], 
            'fear': result[6], 'persona': result[7], 'inconsistency_reason': result[8]
        }
    return None
    
def delete_user_data(user_id: int):
    """Apaga os dados de perfil e de atividade de um usuário."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM daily_plans WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM trades WHERE user_id = ?", (user_id,))
    # Opcional: Apagar também o log de interações
    # cursor.execute("DELETE FROM interactions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"Dados do usuário {user_id} foram redefinidos.")


def save_daily_plan(user_id: int, plan_text: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("""
    INSERT INTO daily_plans (user_id, plan_date, plan_text) VALUES (?, ?, ?)
    ON CONFLICT(user_id, plan_date) DO UPDATE SET plan_text = excluded.plan_text
    """, (user_id, today_str, plan_text))
    conn.commit()
    conn.close()
    logger.info(f"Plano diário salvo para o usuário {user_id}.")

def get_todays_plan(user_id: int) -> str | None:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT plan_text FROM daily_plans WHERE user_id = ? AND plan_date = ?", (user_id, today_str))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def save_trade_details(user_id: int, trade_data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO trades (user_id, trade_description, emotion, unplanned_actions, ai_analysis, timestamp)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        trade_data.get('description'),
        trade_data.get('emotion'),
        trade_data.get('actions'),
        trade_data.get('ai_analysis'),
        datetime.now().isoformat()
    ))
    conn.commit()
    conn.close()
    logger.info(f"Detalhes do trade salvos para o usuário {user_id}.")


def add_user_if_not_exists(user_id: int, first_name: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("INSERT INTO users (user_id, first_name, last_update) VALUES (?, ?, ?)",
                       (user_id, first_name, datetime.now().isoformat()))
        logger.info(f"Novo usuário adicionado: {user_id} ({first_name})")
    conn.commit()
    conn.close()

def check_interaction_limit(user_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')
    cursor.execute("SELECT COUNT(*) FROM interactions WHERE user_id = ? AND date(timestamp) = ?", (user_id, today_str))
    count = cursor.fetchone()[0]
    conn.close()

    if count >= MAX_INTERACTIONS_PER_DAY:
        logger.warning(f"Usuário {user_id} atingiu o limite de interações.")
        return False
    return True

def log_interaction(user_id: int, command: str, user_message: str, ai_response: str):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO interactions (user_id, command, user_message, ai_response, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, command, user_message, ai_response, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"Interação registrada para o usuário {user_id} com o comando {command}.")

# --- Função de Integração com a IA (Gemini) ---

async def get_ai_feedback(lang: str, prompt_context: str, user_input: str | dict, profile_data: dict | None = None, mode: str = 'diagnose') -> str:
    """Gera feedback comportamental usando a API do Gemini com o novo prompt de elite."""
    try:
        persona = profile_data.get('persona', 'male')
        mentor_name = PERSONAS.get(lang, {}).get(persona, 'Mentor')
        system_prompt_key = f'ai_system_prompt_{persona}'
        system_prompt = get_text(system_prompt_key, lang, mentor_name=mentor_name)
        
        task_prompt = ""
        if mode == 'diagnose':
            task_prompt = get_text('ai_task_diagnose', lang)
        elif mode == 'improve':
            task_prompt = get_text('ai_task_improve', lang)
        elif mode == 'affirmation':
            task_prompt = get_text('ai_task_affirmation', lang)
        
        profile_context = ""
        if profile_data:
            # Contexto focado para evitar repetição
            profile_context = f"- Perfil do Trader: Objetivo Principal='{profile_data.get('goal')}', Maior Fraqueza/Medo='{profile_data.get('fear')}'."
            if profile_data.get('inconsistency_reason'):
                profile_context += f" Razão auto-percebida para inconsistência='{profile_data.get('inconsistency_reason')}'."


        prompt_data = ""
        if isinstance(user_input, dict): # Para o postrade detalhado
            prompt_data = (
                f"Contexto: {prompt_context}\n"
                f"- Descrição da Operação: '{user_input.get('description')}'\n"
                f"- Emoção Predominante: '{user_input.get('emotion')}'\n"
                f"- Ações Não Planejadas: '{user_input.get('actions')}'\n\n"
                f"- Tarefa Adicional: Analise a conexão entre a emoção e as ações não planejadas. Qual crença raiz (medo de perder, euforia, não merecimento) provavelmente causou este comportamento?"
            )
        else: # Para outros comandos
            todays_plan = profile_data.get('todays_plan') if profile_data else None
            prompt_data = f"Contexto: {prompt_context}\n- Resposta do trader: '{user_input}'"
            if todays_plan:
                prompt_data = f"Plano original do trader para hoje: '{todays_plan}'\n- Contexto: {prompt_context}\n- Reflexão de fim de dia do trader: '{user_input}'\n\n- Tarefa Adicional: Analise especificamente a aderência do trader ao seu plano original. Aponte onde ele seguiu o plano e onde desviou, e qual o padrão comportamental por trás disso."

        full_prompt = f"{system_prompt}\n\n{task_prompt}\n\n💬 DADOS DO USUÁRIO:\n{profile_context}\n{prompt_data}"

        response = model.generate_content(full_prompt)
        return response.text.strip()
    except Exception as e:
        logger.error(f"Erro ao chamar a API do Gemini: {e}")
        return "Houve um problema ao analisar sua resposta. Por favor, tente novamente mais tarde."

# --- Handlers do Telegram ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    add_user_if_not_exists(user.id, user.first_name)
    lang = get_user_language(user.id)
    profile = get_user_profile(user.id)

    if not profile:
        # Se não tem perfil, também não tem idioma definido. Pergunta primeiro.
        reply_keyboard = [["Português 🇧🇷"], ["English 🇺🇸"], ["Español 🇪🇸"]]
        await update.message.reply_text(
            get_text('choose_language', lang),
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
        )
        return ASKING_LANGUAGE
    else:
        mentor_name = PERSONAS.get(lang, {}).get(profile.get('persona'), 'Mentor')
        await update.message.reply_text(get_text('welcome_back', lang, name=profile.get('name'), goal=profile.get('goal'), fear=profile.get('fear'), mentor_name=mentor_name))
        return ConversationHandler.END

async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Define o idioma e avança para a escolha da persona."""
    user_id = update.effective_user.id
    text = update.message.text
    lang = 'pt' # Default
    if 'English' in text:
        lang = 'en'
    elif 'Español' in text:
        lang = 'es'
    
    set_user_language(user_id, lang)
    context.user_data['lang'] = lang

    personas = PERSONAS.get(lang, {})
    reply_keyboard = [[personas.get('male')], [personas.get('female')]]
    await update.message.reply_text(
        get_text('profile_q_persona', lang),
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASKING_PERSONA

async def set_persona(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Define a persona e avança para o onboarding do perfil."""
    lang = context.user_data.get('lang', 'pt')
    text = update.message.text
    
    persona = 'male' # Default
    if text == PERSONAS.get(lang, {}).get('female'):
        persona = 'female'
    
    context.user_data['persona'] = persona
    await update.message.reply_text(get_text('profile_q_name', lang), reply_markup=ReplyKeyboardRemove())
    return ASKING_PROFILE_NAME


async def check_profile_before_command(update: Update, context: ContextTypes.DEFAULT_TYPE, next_function):
    """Wrapper para verificar se o perfil existe antes de rodar um comando."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    if get_user_profile(user_id):
        return await next_function(update, context)
    else:
        await update.message.reply_text(get_text('profile_needed', lang))
        return ConversationHandler.END

# --- Fluxo de Conversa Genérico ---
async def generic_start(update: Update, context: ContextTypes.DEFAULT_TYPE, question_key: str, next_state: int, **kwargs) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    if not check_interaction_limit(user_id):
        await update.message.reply_text(get_text('limit_reached', lang))
        return ConversationHandler.END
    await update.message.reply_text(get_text(question_key, lang, **kwargs))
    return next_state

async def end_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Finaliza uma interação e mostra o próximo passo."""
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    await update.message.reply_text(get_text('next_step_prompt', lang))
    return ConversationHandler.END

# --- Fluxos de Conversa Específicos ---

# PERFIL
async def profile_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_language(update.effective_user.id)
    context.user_data['lang'] = lang
    
    personas = PERSONAS.get(lang, {})
    reply_keyboard = [[personas.get('male')], [personas.get('female')]]
    await update.message.reply_text(
        get_text('profile_q_persona', lang),
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True),
    )
    return ASKING_PERSONA

async def profile_name_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['name'] = update.message.text
    lang = context.user_data.get('lang', 'pt')
    return await generic_start(update, context, 'profile_q_age', ASKING_PROFILE_AGE, name=context.user_data['name'])

async def profile_age_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['age'] = update.message.text
    return await generic_start(update, context, 'profile_q_experience', ASKING_PROFILE_EXPERIENCE)

async def profile_experience_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['experience'] = update.message.text
    return await generic_start(update, context, 'profile_q_satisfaction', ASKING_PROFILE_SATISFACTION)

async def profile_satisfaction_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = context.user_data.get('lang', 'pt')
    satisfaction_response = update.message.text
    context.user_data['satisfaction'] = satisfaction_response

    # Lógica condicional
    dissatisfied_keywords = ['não', 'not', 'no', 'poderia', 'could', 'além']
    if any(keyword in satisfaction_response.lower() for keyword in dissatisfied_keywords):
        return await generic_start(update, context, 'profile_q_reason', ASKING_PROFILE_REASON)
    else:
        context.user_data['inconsistency_reason'] = None # Garante que o campo está nulo
        return await generic_start(update, context, 'profile_q_source', ASKING_PROFILE_SOURCE)

async def profile_reason_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['inconsistency_reason'] = update.message.text
    return await generic_start(update, context, 'profile_q_source', ASKING_PROFILE_SOURCE)

async def profile_source_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['source'] = update.message.text
    return await generic_start(update, context, 'profile_q_goal', ASKING_PROFILE_GOAL)

async def profile_goal_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['goal'] = update.message.text
    return await generic_start(update, context, 'profile_q_fear', ASKING_PROFILE_FEAR)

async def profile_fear_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = context.user_data.get('lang', 'pt')
    context.user_data['fear'] = update.message.text
    
    profile_data = {
        'name': context.user_data.get('name'),
        'age': context.user_data.get('age'),
        'experience': context.user_data.get('experience'),
        'satisfaction': context.user_data.get('satisfaction'),
        'source': context.user_data.get('source'),
        'goal': context.user_data.get('goal'),
        'fear': context.user_data.get('fear'),
        'persona': context.user_data.get('persona'),
        'inconsistency_reason': context.user_data.get('inconsistency_reason')
    }
    save_user_profile(user_id, profile_data)

    await update.message.reply_text(get_text('profile_complete', lang, name=profile_data['name'], goal=profile_data['goal'], fear=profile_data['fear'], community_link=COMMUNITY_LINK))
    context.user_data.clear()
    return ConversationHandler.END

# PRETRADE
async def pretrade_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    profile = get_user_profile(user_id)
    return await generic_start(update, context, 'pretrade_q_plan', ASKING_PRETRADE, fear=profile.get('fear'))

async def pretrade_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    plan_text = update.message.text
    
    if len(plan_text) < MIN_ANSWER_LENGTH:
        await update.message.reply_text(get_text('elaboration_needed', lang))
        return ASKING_PRETRADE

    profile = get_user_profile(user_id)
    save_daily_plan(user_id, plan_text)
    
    await update.message.reply_text(get_text('pretrade_analyzing', lang))
    ai_feedback = await get_ai_feedback(lang, "O trader está definindo seu plano para o dia (pré-mercado).", plan_text, profile_data=profile, mode='diagnose')
    
    context.user_data['plan_text'] = plan_text
    context.user_data['initial_diagnosis'] = ai_feedback
    
    await update.message.reply_text(ai_feedback)
    log_interaction(user_id, "pretrade_diagnosis", plan_text, ai_feedback)
    
    await update.message.reply_text(get_text('pretrade_confirm_diagnosis', lang))
    return AWAITING_PRETRADE_CONFIRMATION

async def pretrade_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_response = update.message.text.lower()
    lang = get_user_language(update.effective_user.id)

    if 'sim' in user_response or 'yes' in user_response or 'sí' in user_response:
        diagnosis = context.user_data.get('initial_diagnosis', '')
        points = re.findall(r"^\d+\.\s.*", diagnosis, re.MULTILINE)
        
        if not points:
            await update.message.reply_text(get_text('pretrade_no_points', lang))
            return await end_interaction(update, context)

        context.user_data['diagnosis_points'] = points
        
        await update.message.reply_text(get_text('pretrade_choose_focus', lang, points="\n".join(points)))
        return AWAITING_FOCUS_CHOICE
    else:
        await update.message.reply_text(get_text('Entendido. Foco no plano. Um ótimo dia de operações.', lang))
        context.user_data.clear()
        return await end_interaction(update, context)

async def pretrade_focus_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    profile = get_user_profile(user_id)
    choices_text = update.message.text
    
    try:
        selected_indices = [int(i.strip()) - 1 for i in choices_text.split(',') if i.strip().isdigit()]
        
        if len(selected_indices) != 1:
            await update.message.reply_text(get_text('pretrade_invalid_choice', lang))
            return AWAITING_FOCUS_CHOICE

        all_points = context.user_data.get('diagnosis_points', [])
        selected_point_index = selected_indices[0]
        
        if not (0 <= selected_point_index < len(all_points)):
            await update.message.reply_text(get_text('pretrade_invalid_number', lang, number=selected_point_index + 1))
            return AWAITING_FOCUS_CHOICE

        selected_point = all_points[selected_point_index]

        await update.message.reply_text(get_text('pretrade_action_plan_generating', lang))
        
        plan_text = context.user_data.get('plan_text')
        
        action_plan = await get_ai_feedback(
            lang,
            "Criação de plano de ação pré-mercado focado.", 
            selected_point, 
            profile_data={'todays_plan': plan_text, **profile}, 
            mode='improve'
        )
        
        await update.message.reply_text(action_plan)
        log_interaction(user_id, "pretrade_action_plan", "Ponto escolhido: " + str(selected_point_index + 1), action_plan)
        
        await update.message.reply_text(get_text('pretrade_eod_instruction', lang))

    except Exception as e:
        logger.error(f"Erro ao processar escolha de foco: {e}")
        await update.message.reply_text("Ocorreu um erro ao processar sua escolha. Tente novamente.")

    context.user_data.clear()
    return ConversationHandler.END

# POSTRADE
async def postrade_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await generic_start(update, context, 'postrade_q_details', ASKING_POSTRADE_DETAILS)

async def postrade_details_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_language(update.effective_user.id)
    text = update.message.text
    if len(text) < MIN_ANSWER_LENGTH:
        await update.message.reply_text(get_text('elaboration_needed', lang))
        return ASKING_POSTRADE_DETAILS
    context.user_data['trade_description'] = text
    return await generic_start(update, context, 'postrade_q_emotion', ASKING_POSTRADE_EMOTION)

async def postrade_emotion_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['trade_emotion'] = update.message.text
    return await generic_start(update, context, 'postrade_q_actions', ASKING_POSTRADE_ACTIONS)

async def postrade_actions_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    context.user_data['trade_actions'] = update.message.text
    profile = get_user_profile(user_id)
    trade_data = {
        'description': context.user_data.get('trade_description'),
        'emotion': context.user_data.get('trade_emotion'),
        'actions': context.user_data.get('trade_actions'),
    }
    await update.message.reply_text(get_text('postrade_analyzing', lang))
    ai_feedback = await get_ai_feedback(lang, "Análise profunda de uma operação executada.", trade_data, profile_data=profile, mode='diagnose')
    await update.message.reply_text(ai_feedback)
    trade_data['ai_analysis'] = ai_feedback
    save_trade_details(user_id, trade_data)
    log_interaction(user_id, "postrade", str(trade_data), ai_feedback)
    context.user_data.clear()
    return await end_interaction(update, context)

# EOD
async def eod_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    profile = get_user_profile(user_id)
    todays_plan = get_todays_plan(user_id)
    context.user_data['todays_plan'] = todays_plan
    
    question_key = 'eod_q_generic'
    kwargs = {'goal': profile.get('goal'), 'fear': profile.get('fear')}
    if todays_plan:
        question_key = 'eod_q_plan'
        kwargs['plan'] = todays_plan

    return await generic_start(update, context, question_key, ASKING_EOD, **kwargs)

async def eod_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    user_response = update.message.text
    if len(user_response) < MIN_ANSWER_LENGTH:
        await update.message.reply_text(get_text('elaboration_needed', lang))
        return ASKING_EOD
    profile = get_user_profile(user_id)
    todays_plan = context.user_data.get('todays_plan')
    profile['todays_plan'] = todays_plan
    
    await update.message.reply_text(get_text('eod_analyzing', lang))
    ai_feedback = await get_ai_feedback(lang, "O trader está fazendo sua revisão de fim de dia (EOD), comparando com seu plano.", user_response, profile_data=profile, mode='diagnose')
    
    await update.message.reply_text(ai_feedback)
    log_interaction(user_id, "eod", user_response, ai_feedback)
    return await end_interaction(update, context)

# DORMIR
async def dormir_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await generic_start(update, context, 'dormir_q', ASKING_DORMIR)

async def dormir_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    user_response = update.message.text
    profile = get_user_profile(user_id)
    await update.message.reply_text(get_text('dormir_processing', lang))
    ai_feedback = await get_ai_feedback(lang, "Geração de afirmações para o sono.", user_response, profile_data=profile, mode='affirmation')
    await update.message.reply_text(ai_feedback)
    log_interaction(user_id, "dormir", user_response, ai_feedback)
    return await end_interaction(update, context)

# REDEFINIR
async def redefine_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_language(update.effective_user.id)
    await update.message.reply_text(get_text('redefine_confirm', lang))
    return AWAITING_REDEFINE_CONFIRMATION

async def redefine_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    response = update.message.text.lower()

    if 'sim' in response or 'yes' in response or 'sí' in response:
        delete_user_data(user_id)
        await update.message.reply_text(get_text('redefine_success', lang))
    else:
        await update.message.reply_text(get_text('redefine_cancel', lang))
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    lang = get_user_language(update.effective_user.id)
    context.user_data.clear()
    await update.message.reply_text(get_text('cancel_conversation', lang), reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main() -> None:
    init_db()
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Handler unificado para todas as conversas
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("perfil", profile_start),
            CommandHandler("redefinir", redefine_start),
            CommandHandler("pretrade", lambda u, c: check_profile_before_command(u, c, pretrade_start)),
            CommandHandler("postrade", lambda u, c: check_profile_before_command(u, c, postrade_start)),
            CommandHandler("eod", lambda u, c: check_profile_before_command(u, c, eod_start)),
            CommandHandler("dormir", lambda u, c: check_profile_before_command(u, c, dormir_start)),
        ],
        states={
            # Estados do Onboarding
            ASKING_LANGUAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_language)],
            ASKING_PERSONA: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_persona)],
            ASKING_PROFILE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_name_response)],
            ASKING_PROFILE_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_age_response)],
            ASKING_PROFILE_EXPERIENCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_experience_response)],
            ASKING_PROFILE_SATISFACTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_satisfaction_response)],
            ASKING_PROFILE_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_reason_response)],
            ASKING_PROFILE_SOURCE: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_source_response)],
            ASKING_PROFILE_GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_goal_response)],
            ASKING_PROFILE_FEAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, profile_fear_response)],
            
            # Estado para redefinir perfil
            AWAITING_REDEFINE_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, redefine_confirm)],

            # Estados para o fluxo do pretrade
            ASKING_PRETRADE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pretrade_response)],
            AWAITING_PRETRADE_CONFIRMATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, pretrade_confirmation)],
            AWAITING_FOCUS_CHOICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, pretrade_focus_choice)],
            
            # Estados para conversas de um passo
            ASKING_EOD: [MessageHandler(filters.TEXT & ~filters.COMMAND, eod_response)],
            ASKING_DORMIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, dormir_response)],

            # Estados para a conversa de múltiplos passos do postrade
            ASKING_POSTRADE_DETAILS: [MessageHandler(filters.TEXT & ~filters.COMMAND, postrade_details_response)],
            ASKING_POSTRADE_EMOTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, postrade_emotion_response)],
            ASKING_POSTRADE_ACTIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, postrade_actions_response)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    
    async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
        lang = get_user_language(update.effective_user.id)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=get_text('unknown_command', lang))
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    logger.info("Mentor comportamental de elite iniciado...")
    application.run_polling()

if __name__ == "__main__":
    main()
