"""User-facing Turkish strings.

Keep every string that a human will read in this module (or in the frontend
i18n files). Code, comments and log messages stay in English.
"""

from __future__ import annotations

from typing import Final

# --- Genel ---
APP_NAME: Final = "TraceHub"
APP_TAGLINE: Final = "Salt okunur DevOps teşhis asistanı"

# --- Hata mesajları ---
ERR_UNKNOWN_ENVIRONMENT: Final = (
    "'{environment}' adında tanımlı bir ortam yok. Tanımlı ortamlar: {allowed}"
)
ERR_NOT_ALLOWED: Final = "Bu işlem güvenlik politikası tarafından engellendi: {reason}"
ERR_BUDGET_EXCEEDED: Final = (
    "Araştırma bütçesi doldu ({limit}). Elde edilen bulgularla rapor hazırlanıyor."
)
ERR_LLM_UNAVAILABLE: Final = (
    "Dil modeline ulaşılamadı. Yapılandırmayı ve model sunucusunun durumunu kontrol edin."
)
ERR_KB_EMPTY: Final = "Bilgi tabanı boş görünüyor. 'tracehub kb ingest' komutunu çalıştırdınız mı?"

# --- Bilgi tabanı doğrulama ---
KB_VALIDATION_OK: Final = "{count} doküman doğrulandı, hata yok."
KB_VALIDATION_FAILED: Final = "{count} dokümanda hata bulundu."
KB_INGEST_DONE: Final = "{docs} doküman, {chunks} parça olarak indekslendi."

# --- Ajan akışı ---
PLAN_HEADER: Final = "Önerilen araştırma planı"
PLAN_APPROVAL_PROMPT: Final = (
    "Bu planı onaylıyor musunuz? Adımları düzenleyebilir veya reddedebilirsiniz."
)
PLAN_REJECTED: Final = "Plan reddedildi. Araştırma başlatılmadı."
INVESTIGATION_STARTED: Final = "Araştırma başladı. Adımlar canlı olarak aşağıda görünecek."
INVESTIGATION_STOPPED: Final = "Araştırma kullanıcı tarafından durduruldu."
REPORT_HEADER: Final = "Bulgular ve öneriler"

# --- Değişiklik uyarıları (rapor sonunda hatırlatılır) ---
WARN_READ_ONLY: Final = "TraceHub hiçbir değişiklik yapmaz. Aşağıdaki adımları siz uygulamalısınız."
WARN_APPROVAL_REQUIRED: Final = (
    "Bu işlem için onay gerekiyor. İlgili onayların alındığını doğrulayın."
)
WARN_PRODUCTION: Final = (
    "DİKKAT: Bu adım üretim (production) ortamını etkiliyor. "
    "Değişiklik penceresi ve geri alma planı olmadan uygulamayın."
)
