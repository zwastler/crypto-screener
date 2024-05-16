from .binance import binance_wss
from .bybit import bybit_wss
from .gate import gate_wss
from .htx import htx_wss
from .okx import okx_wss

adapters_list = {
    "bybit": bybit_wss.wss_connect,
    "binance": binance_wss.wss_connect,
    "gate": gate_wss.wss_connect,
    "okx": okx_wss.wss_connect,
    "htx": htx_wss.wss_connect,
}
