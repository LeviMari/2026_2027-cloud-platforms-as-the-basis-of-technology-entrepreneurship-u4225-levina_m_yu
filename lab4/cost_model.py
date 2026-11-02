H = 730            # часов в месяце
S = H * 3600       # секунд в месяце
# --- цены (USD, us-central1, ноябрь 2026) ---
GEM_IN, GEM_OUT, EMB = 0.30, 2.50, 0.15            # $ за 1M токенов
RUN_CPU_ACT, RUN_MEM_ACT = 0.000024, 0.0000025     # $/vCPU-s, $/GiB-s (request-based)
RUN_CPU_IDLE, RUN_MEM_IDLE = 0.0000025, 0.0000025  # min instances в простое
RUN_REQ = 0.40                                      # $ за 1M запросов
FREE_CPU, FREE_MEM, FREE_REQ = 180_000, 360_000, 2_000_000
SQL_VCPU, SQL_MEM, SQL_HA_VCPU, SQL_HA_MEM = 0.0413, 0.007, 0.0826, 0.014
SQL_F1 = 0.0105
SSD, SSD_HA, BKP = 0.000232877 * H, 0.000465753 * H, 0.000109589 * H  # $/GiB-мес
REDIS_BASIC = 0.049                                 # $/GiB-ч, M1
LB_RULE, LB_GB = 0.025, 0.008
ARMOR_POLICY, ARMOR_RULE, ARMOR_REQ = 5.0, 1.0, 0.75
GCS = 0.020                                         # $/GB-мес Standard

# --- профиль диалога ---
MSG_PER_DIALOG = 4
IN_TOK, OUT_TOK = 3000, 300        # на одно сообщение: промпт+найденные фрагменты+история / ответ
Q_EMB_TOK = 50
SEC_PER_MSG = 3                    # время обработки (ждём ответ модели)

def llm(dialogs, cache_hit=0.0):
    m = dialogs * MSG_PER_DIALOG * (1 - cache_hit)
    gen = m * (IN_TOK * GEM_IN + OUT_TOK * GEM_OUT) / 1e6
    emb = dialogs * MSG_PER_DIALOG * Q_EMB_TOK * EMB / 1e6
    return gen, emb

def run(dialogs, vcpu, mem, min_inst, concurrency):
    msgs = dialogs * MSG_PER_DIALOG
    inst_s = msgs * SEC_PER_MSG / concurrency
    cpu = max(0, inst_s * vcpu - FREE_CPU) * RUN_CPU_ACT
    memc = max(0, inst_s * mem - FREE_MEM) * RUN_MEM_ACT
    idle = min_inst * S * (vcpu * RUN_CPU_IDLE + mem * RUN_MEM_IDLE)
    req = max(0, msgs * 1.25 - FREE_REQ) * RUN_REQ / 1e6
    return cpu + memc + idle + req

def stage(name, dialogs, shops, items):
    total = sum(v for _, v, _ in items)
    print(f"\n### {name}: {dialogs:,} диалогов/мес, {shops} маг.")
    print("| Сервис | Конфигурация | $/мес |\n|---|---|---|")
    for k, v, conf in items:
        print(f"| {k} | {conf} | {v:,.2f} |")
    print(f"| **Итого** | | **{total:,.0f}** |")
    print(f"На 1 диалог: ${total/dialogs:.4f}; на магазин: ${total/shops:,.0f}")
    return total

# ---------- Этап 1 ----------
d1 = 1_000
g, e = llm(d1)
t1 = stage("Этап 1", d1, 1, [
    ("Vertex AI Gemini 2.5 Flash", g, "4 сообщения × (3 000 вход + 300 выход токенов)"),
    ("Vertex AI embeddings", e + 0.15, "вопросы + индексация базы 1 млн токенов"),
    ("Cloud Run", run(d1, 1, 0.5, 0, 10), "min 0, max 2, 1 vCPU / 512 MiB — в бесплатном лимите"),
    ("Cloud SQL PostgreSQL", SQL_F1 * H + 10 * SSD + 10 * BKP, "db-f1-micro, 10 GB SSD, бэкапы"),
    ("Cloud Storage", 1 * GCS, "1 GB"),
    ("Secret Manager, Logging, Monitoring", 0.30, "3 секрета; логи в бесплатных 50 GiB"),
])
# ---------- Этап 2 ----------
d2 = 15_000
g, e = llm(d2)
t2 = stage("Этап 2", d2, 5, [
    ("Vertex AI Gemini 2.5 Flash", g, "15 000 диалогов"),
    ("Vertex AI embeddings", e + 5 * 4 * 1 * EMB, "вопросы + ночная переиндексация 5 магазинов"),
    ("Cloud Run", run(d2, 1, 0.5, 1, 10), "min 1 (без холодного старта), 1 vCPU / 512 MiB"),
    ("Cloud SQL PostgreSQL", (SQL_VCPU + 3.75 * SQL_MEM) * H + 20 * SSD + 20 * BKP, "1 vCPU / 3,75 GB (SLA), 20 GB, бэкапы"),
    ("Cloud Storage", 10 * GCS, "10 GB"),
    ("Cloud Build, Artifact Registry", 1.0, "CI/CD, ~30 сборок"),
    ("Cloud Scheduler, Secret Manager, Monitoring", 0.60, "1 задание, секреты, алерты"),
])
# ---------- Этап 3 ----------
d3 = 300_000
CACHE = 0.25
g, e = llm(d3)
g_opt, _ = llm(d3, CACHE)
items3 = [
    ("Vertex AI Gemini 2.5 Flash", g, "300 000 диалогов"),
    ("Vertex AI embeddings", e + 100 * 4 * 1 * EMB, "вопросы + еженедельная переиндексация 100 магазинов"),
    ("Cloud Run", run(d3, 2, 1, 2, 20), "min 2, max 20, 2 vCPU / 1 GiB"),
    ("Cloud SQL PostgreSQL HA", (2 * SQL_HA_VCPU + 7.5 * SQL_HA_MEM) * H + 100 * SSD_HA + 100 * BKP, "HA 2 vCPU / 7,5 GB, 100 GB"),
    ("Memorystore Redis", REDIS_BASIC * H, "Basic 1 GB"),
    ("Cloud Load Balancing", LB_RULE * H + 100 * LB_GB * 2, "1 правило, ~100 GB трафика"),
    ("Cloud Armor", ARMOR_POLICY + 5 * ARMOR_RULE + 1.5 * ARMOR_REQ, "1 политика, 5 правил, 1,5 млн запросов"),
    ("Cloud CDN + исходящий трафик", 8.0, "~100 GB (виджет, ответы)"),
    ("Cloud Storage", 200 * GCS, "200 GB"),
    ("BigQuery", 5.0, "~50 GB хранения, запросы в бесплатном 1 ТБ"),
    ("Cloud Logging", 25.0, "~100 GiB логов (50 GiB бесплатно)"),
    ("Pub/Sub, Scheduler, Secret Manager, Build", 6.0, "в основном бесплатные лимиты"),
]
t3 = stage("Этап 3", d3, 100, items3)
sql_cud = (2 * 0.06195 + 7.5 * 0.0105) * H + 100 * SSD_HA + 100 * BKP
sql_od = items3[3][1]
opt = t3 - (g - g_opt) - (sql_od - sql_cud) + 0
print(f"\nОптимизация этапа 3: кэш {CACHE:.0%} экономит ${g-g_opt:,.0f}, CUD 1 год на SQL экономит ${sql_od-sql_cud:,.0f} -> ${opt:,.0f}")
print(f"LLM на диалог: ${ (MSG_PER_DIALOG*(IN_TOK*GEM_IN+OUT_TOK*GEM_OUT)/1e6):.4f}")
