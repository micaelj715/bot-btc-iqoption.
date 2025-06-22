from iqoptionapi.stable_api import IQ_Option
import time
import datetime
import requests
import pandas as pd

# --- Configurações ---
EMAIL = "micaelrocha677@gmail.com"
SENHA = "micael2040"
TOKEN = "8061501501:AAEJQnqgFiW1djGJ7aZ1hlCrNOhF6yqU_mk"
CHAT_ID = "5193079733"
TELEGRAM_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

ATIVOS_BTC = ["BTCUSD"]
ATIVOS_EURUSD = ["EURUSD-OTC"]
TIMEFRAMES_EURUSD = [1, 5]  # minutos

STOP_LOSS_PERCENT = 0.3
TARGET_PERCENT = 0.5

iq = IQ_Option(EMAIL, SENHA)
iq.connect()
if not iq.check_connect():
    print("Erro ao conectar!")
    exit()
print("Conectado com sucesso!")

# --- Variáveis globais ---
green_count = 0
loss_count = 0

# --- Telegram ---
def send_telegram(text):
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(TELEGRAM_URL, data=payload)
    except Exception as e:
        print("Erro ao enviar Telegram:", e)

# --- Indicadores ---
def calcular_rsi(df, periodo=14):
    delta = df.diff()
    ganho = delta.clip(lower=0).rolling(window=periodo).mean()
    perda = -delta.clip(upper=0).rolling(window=periodo).mean()
    rs = ganho / perda
    return 100 - (100 / (1 + rs))

def calcular_ema(df, periodo=10):
    return df.ewm(span=periodo, adjust=False).mean()

# --- Envio de sinais formatados (Telegram) ---
def enviar_sinal_btc(ativo, direcao, preco_entrada):
    hora = datetime.datetime.now().strftime("%H:%M")
    emoji = "🟢" if "COMPRA" in direcao else "🔴"
    mensagem = f"""
<b>🚀 NOVO SINAL LONGO PRAZO BTC</b>
{emoji} <b>{direcao}</b>
<b>Ativo:</b> {ativo}
<b>Preço de Entrada:</b> <code>{preco_entrada:.2f}</code>
<b>Hora:</b> {hora}
<b>⏳ Monitorando alvo e stop loss... ⏳</b>

#BTC #LongoPrazo
"""
    send_telegram(mensagem)

def enviar_resultado_btc(ativo, direcao, preco_fechamento, resultado):
    emoji = "✅" if resultado.startswith("GREEN") else "❌"
    hora = datetime.datetime.now().strftime("%H:%M")
    mensagem = f"""
<b>🎯 FECHAR POSIÇÃO BTC</b>
{emoji} <b>{direcao} finalizada: {resultado}</b>
<b>Ativo:</b> {ativo}
<b>Preço de Fechamento:</b> <code>{preco_fechamento:.2f}</code>
<b>Hora:</b> {hora}

#BTC #Resultado
"""
    send_telegram(mensagem)

def enviar_sinal_eurusd(ativo, timeframe, direcao):
    hora = datetime.datetime.now().strftime("%H:%M")
    emoji = "🟢" if "COMPRA" in direcao else "🔴"
    mensagem = f"""
<b>✨ NOVO SINAL - {ativo} {timeframe}M</b>
{emoji} <b>{direcao}</b>
🕒 {hora}

#EURUSD #CurtoPrazo
"""
    send_telegram(mensagem)

def enviar_resultado_eurusd(ativo, timeframe, resultado):
    emoji = "✅" if resultado == "GREEN" else "❌"
    hora = datetime.datetime.now().strftime("%H:%M")
    mensagem = f"""
<b>📊 RESULTADO - {ativo} {timeframe}M</b>
{emoji} <b>{resultado}</b>
🕒 {hora}

#EURUSD #Resultado
"""
    send_telegram(mensagem)

def enviar_relatorio():
    mensagem = f"""
<b>📈 RELATÓRIO DE OPERAÇÕES</b>
✅ Green: {green_count}
❌ Loss: {loss_count}
"""
    send_telegram(mensagem)

def check_stop_loss(preco_entrada, preco_atual, direcao):
    if direcao == "COMPRA" and preco_atual <= preco_entrada * (1 - STOP_LOSS_PERCENT / 100):
        return True
    if direcao == "VENDA" and preco_atual >= preco_entrada * (1 + STOP_LOSS_PERCENT / 100):
        return True
    return False

def monitorar_btc():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Procurando sinais BTC...")
    for ativo in ATIVOS_BTC:
        velas = iq.get_candles(ativo, 60*60, 100, time.time())
        if not velas or len(velas) < 15:
            continue
        df = pd.DataFrame(velas)
        df['close'] = df['close'].astype(float)
        rsi = calcular_rsi(df['close'])
        ema = calcular_ema(df['close'])
        candle = df.iloc[-1]
        prev = df.iloc[-2]

        direcao = None
        if rsi.iloc[-1] < 30 and prev['close'] < ema.iloc[-2] and candle['close'] > ema.iloc[-1]:
            direcao = "COMPRA"
        elif rsi.iloc[-1] > 70 and prev['close'] > ema.iloc[-2] and candle['close'] < ema.iloc[-1]:
            direcao = "VENDA"

        if direcao:
            preco_entrada = candle['close']
            enviar_sinal_btc(ativo, direcao, preco_entrada)
            inicio = time.time()
            while True:
                time.sleep(10)
                if time.time() - inicio > 3600:
                    break
                candles_atuais = iq.get_candles(ativo, 60, 1, time.time())
                if not candles_atuais:
                    continue
                preco_atual = candles_atuais[-1]['close']
                if check_stop_loss(preco_entrada, preco_atual, direcao):
                    global loss_count
                    loss_count += 1
                    enviar_resultado_btc(ativo, direcao, preco_atual, "LOSS (Stop Loss)")
                    enviar_relatorio()
                    break
                if direcao == "COMPRA" and preco_atual >= preco_entrada * (1 + TARGET_PERCENT / 100):
                    global green_count
                    green_count += 1
                    enviar_resultado_btc(ativo, direcao, preco_atual, "GREEN (Alvo Atingido)")
                    enviar_relatorio()
                    break
                elif direcao == "VENDA" and preco_atual <= preco_entrada * (1 - TARGET_PERCENT / 100):
                    green_count += 1
                    enviar_resultado_btc(ativo, direcao, preco_atual, "GREEN (Alvo Atingido)")
                    enviar_relatorio()
                    break

def analisar_e_enviar_eurusd():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Procurando sinais EURUSD...")
    for ativo in ATIVOS_EURUSD:
        for tf in TIMEFRAMES_EURUSD:
            velas = iq.get_candles(ativo, tf * 60, 100, time.time())
            if not velas or len(velas) < 15:
                continue
            df = pd.DataFrame(velas)
            df['close'] = df['close'].astype(float)
            df['open'] = df['open'].astype(float)
            rsi = calcular_rsi(df['close'])
            ema = calcular_ema(df['close'])
            candle = df.iloc[-1]
            prev = df.iloc[-2]

            direcao = None
            if rsi.iloc[-1] < 30 and prev['close'] < ema.iloc[-2] and candle['close'] > ema.iloc[-1]:
                direcao = "📈 COMPRA"
            elif rsi.iloc[-1] > 70 and prev['close'] > ema.iloc[-2] and candle['close'] < ema.iloc[-1]:
                direcao = "📉 VENDA"

            if direcao:
                enviar_sinal_eurusd(ativo, tf, direcao)
                print(f"Aguardando fechamento do candle {ativo} {tf}M...")
                time.sleep(tf * 60)
                nova = iq.get_candles(ativo, tf * 60, 2, time.time())
                if not nova or len(nova) < 2:
                    continue
                c1 = nova[-2]
                c2 = nova[-1]
                resultado = None
                global green_count, loss_count
                if "COMPRA" in direcao:
                    resultado = "GREEN" if c2['close'] > c1['open'] else "LOSS"
                else:
                    resultado = "GREEN" if c2['close'] < c1['open'] else "LOSS"
                if resultado == "GREEN":
                    green_count += 1
                else:
                    loss_count += 1
                enviar_resultado_eurusd(ativo, tf, resultado)
                enviar_relatorio()

# --- Loop principal com status ---
send_telegram("🤖 Bot iniciado e procurando sinais em tempo real...")
last_ping = time.time()

while True:
    try:
        if time.time() - last_ping > 3600:
            send_telegram("📡 Bot ainda operando e monitorando ativos...")
            last_ping = time.time()

        monitorar_btc()
        analisar_e_enviar_eurusd()
        time.sleep(5)
    except Exception as e:
        print("Erro:", e)
        time.sleep(10)
