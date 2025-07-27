import os
import time
import datetime
import logging
from typing import Dict, Tuple, Optional, List

try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    raise ImportError("Não foi possível importar IQ_Option. Instale a lib iqoptionapi.")

import requests
import statistics

# Configurações (variáveis ambiente)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7882045313:AAGlPjCV55XF_oxcQkTQG-y139xAYGQy70I")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-4811582496")
EMAIL = os.getenv("IQ_EMAIL", "micaeldejesusrocha@gmail.com")
SENHA = os.getenv("IQ_SENHA", "Micael2040@")

COOLDOWN_SEGUNDOS = 120
BLOQUEAR_REPETICAO_MESMA_VELA = True

logging.basicConfig(level=logging.ERROR)

def enviar_telegram(msg: str) -> None:
    if not TOKEN or not CHAT_ID or "COLOQUE" in TOKEN:
        print(f"[TELEGRAM MOCK] {msg}")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, data=data, timeout=10)
        if resp.status_code != 200:
            logging.error(f"Falha ao enviar Telegram: {resp.status_code} {resp.text}")
    except Exception as e:
        logging.error(f"Erro ao enviar Telegram: {e}")

def conectar_iq() -> IQ_Option:
    api = IQ_Option(EMAIL, SENHA)
    api.connect()
    while not api.check_connect():
        print("Tentando reconectar na IQ Option...")
        time.sleep(5)
        api.connect()
    api.change_balance("PRACTICE")
    saldo = api.get_balance()
    print(f"✅ Conectado na IQ Option. Saldo: ${saldo}")
    enviar_telegram(f"✅ *Robô conectado*\nSaldo: ${saldo}")
    return api

def reconectar(api: IQ_Option) -> None:
    try:
        api.connect()
        while not api.check_connect():
            print("Tentando reconectar na IQ Option...")
            time.sleep(5)
            api.connect()
        api.change_balance("PRACTICE")
        print("✅ Reconectado na IQ Option")
    except Exception as e:
        logging.error(f"Erro reconectar: {e}")

def calcular_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    slice_ = prices[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(slice_)):
        delta = slice_[i] - slice_[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calcular_ema(prices: List[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    slice_ = prices[-period:]
    return sum(slice_) / period

def calcular_bollinger_bands(prices: List[float], period: int, dev_up: float, dev_down: float) -> Optional[dict]:
    if len(prices) < period:
        return None
    slice_ = prices[-period:]
    media = sum(slice_) / period
    desvio = statistics.stdev(slice_)
    upper = media + dev_up * desvio
    lower = media - dev_down * desvio
    return {"upper": upper, "middle": media, "lower": lower}

def extrair_indicadores(candles: List[dict]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    close_prices = [c["close"] for c in candles]
    return calcular_rsi(close_prices), calcular_ema(close_prices, 9), calcular_ema(close_prices, 21)

def obter_payout(api: IQ_Option, par: str) -> float:
    try:
        all_profits = api.get_all_profit()
        if par in all_profits and "binary" in all_profits[par]:
            return float(all_profits[par]["binary"] * 100)
    except Exception as e:
        logging.error(f"Erro ao buscar payout para {par}: {e}")
    return 0.0

def estrategia_tendencia(
    rsi: Optional[float],
    ema9: Optional[float],
    ema21: Optional[float],
    ema9_anterior: Optional[float],
    ema21_anterior: Optional[float],
) -> Optional[str]:
    if None in (rsi, ema9, ema21, ema9_anterior, ema21_anterior):
        return None
    if rsi < 30 and ema9 > ema21 and ema9_anterior <= ema21_anterior:
        return "call"
    if rsi > 70 and ema9 < ema21 and ema9_anterior >= ema21_anterior:
        return "put"
    return None

def estrategia_topo_fundo(candles: List[dict]) -> Optional[str]:
    if len(candles) < 3:
        return None
    c1, c2, c3 = candles[-3], candles[-2], candles[-1]
    if c1["close"] < c2["close"] > c3["close"]:
        return "put"
    if c1["close"] > c2["close"] < c3["close"]:
        return "call"
    return None

def estrategia_bollinger_ema(candles: List[dict], BB_period: int, BB_dev_up: float, BB_dev_down: float, EMA_period: int) -> Optional[str]:
    close_prices = [c["close"] for c in candles]
    if len(close_prices) < max(BB_period, EMA_period) + 1:
        return None
    bb = calcular_bollinger_bands(close_prices, BB_period, BB_dev_up, BB_dev_down)
    ema = calcular_ema(close_prices, EMA_period)
    price_now = close_prices[-1]
    last_bb = calcular_bollinger_bands(close_prices[:-1], BB_period, BB_dev_up, BB_dev_down)
    if not bb or not last_bb or ema is None:
        return None
    if price_now > bb["upper"] and ema > bb["upper"] and close_prices[-2] < last_bb["upper"]:
        return "put"
    if price_now < bb["lower"] and ema < bb["lower"] and close_prices[-2] > last_bb["lower"]:
        return "call"
    return None

def abrir_operacao(api: IQ_Option, ativo: str, direcao: str, valor: float, timeframe: int):
    try:
        return api.buy(valor, ativo, direcao, timeframe)
    except Exception as e:
        logging.error(f"Erro abrir operação: {e}")
        return False, None

def verificar_resultado(api: IQ_Option, id_op):
    try:
        res = api.check_win_v3(id_op)
        if res is None:
            return 0.0
        if isinstance(res, (tuple, list)):
            return float(res[1])
        return float(res)
    except Exception as e:
        logging.error(f"Erro verificar resultado: {e}")
        return 0.0

def pode_enviar_sinal(
    ativo: str,
    direcao: str,
    candle_time: int,
    last_signal_info: Dict[str, dict],
    cooldown: int = COOLDOWN_SEGUNDOS,
    bloquear_mesma_vela: bool = BLOQUEAR_REPETICAO_MESMA_VELA,
) -> bool:
    info = last_signal_info.get(ativo)
    agora = time.time()
    if not info:
        return True
    if bloquear_mesma_vela and info["candle_time"] == candle_time:
        return False
    if info["direcao"] == direcao and (agora - info["ts"]) < cooldown:
        return False
    return True

def registrar_sinal(ativo: str, direcao: str, candle_time: int, last_signal_info: Dict[str, dict]) -> None:
    last_signal_info[ativo] = {"direcao": direcao, "ts": time.time(), "candle_time": candle_time}

def main():
    api = conectar_iq()

    ativos_otc = ["EURUSD-OTC", "GBPUSD-OTC", "EURGBP-OTC", "NZDUSD-OTC"]


    timeframe = 1
    valor_entrada = 1500
    historico_operacoes: List[float] = []
    entradas_realizadas = 0
    limite_entradas = 5000
    ema9_anterior: Dict[str, Optional[float]] = {}
    ema21_anterior: Dict[str, Optional[float]] = {}

    last_signal_info: Dict[str, dict] = {}

    print("🤖 Robô iniciado com estratégias: Bollinger+EMA + Tendência + Topo/Fundo (enviando apenas resultados)")

    while True:
        if not api.check_connect():
            reconectar(api)

        # Filtra pares com payout positivo e ordena
        pares = [
            {"ativo": par, "payout": obter_payout(api, par)}
            for par in ativos_otc
            if obter_payout(api, par) > 0
        ]
        pares_ordenados = sorted(pares, key=lambda x: x["payout"], reverse=True)

        for item in pares_ordenados:
            ativo = item["ativo"]

            if entradas_realizadas >= limite_entradas:
                enviar_telegram("⚠️ Limite diário de entradas atingido. Parando operações.")
                return

            try:
                candles = api.get_candles(ativo, timeframe * 60, 50, time.time())
            except Exception as e:
                logging.error(f"Erro ao buscar candles para {ativo}: {e}")
                continue

            rsi, ema9, ema21 = extrair_indicadores(candles)
            ema9_ant = ema9_anterior.get(ativo)
            ema21_ant = ema21_anterior.get(ativo)

            # Gera sinal
            sinal = estrategia_bollinger_ema(candles, 20, 2, 2, 9) \
                    or estrategia_tendencia(rsi, ema9, ema21, ema9_ant, ema21_ant) \
                    or estrategia_topo_fundo(candles)

            ema9_anterior[ativo] = ema9
            ema21_anterior[ativo] = ema21

            if sinal and pode_enviar_sinal(ativo, sinal, candles[-1]["from"], last_signal_info):
                status, id_op = abrir_operacao(api, ativo, sinal, valor_entrada, timeframe)
                if not status:
                    logging.error(f"Falha ao abrir operação para {ativo}")
                    continue

                registrar_sinal(ativo, sinal, candles[-1]["from"], last_signal_info)
                print(f"✅ Operação enviada: {ativo} | {sinal.upper()} | Aguardando resultado...")

                # Aguarda encerramento da vela
                time.sleep(timeframe * 60)

                # Verifica e envia resultado
                resultado = verificar_resultado(api, id_op)
                historico_operacoes.append(resultado)
                entradas_realizadas += 1

                if resultado > 0:
                    msg = f"🏆🟢 *LUCRO!* {ativo} | {sinal.upper()} | +${round(resultado,2)}"
                elif resultado < 0:
                    msg = f"💔 *PREJUÍZO* {ativo} | {sinal.upper()} | -${abs(round(resultado,2))}"
                else:
                    msg = f"⚖️ *EMPATE* {ativo} | {sinal.upper()} | $0.00"

                print(msg)
                enviar_telegram(msg)

        # Sincroniza para o próximo minuto
        agora = datetime.datetime.now()
        sleep_secs = 60 - agora.second - agora.microsecond / 1_000_000
        time.sleep(sleep_secs)

if __name__ == "__main__":
    print("Iniciando o robô...")
    main()
