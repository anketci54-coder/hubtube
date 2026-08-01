# HubTube

## Technology Benefit Radar — Teknik Şartname v1.0.0

Durum: **Dondurulmuş MVP sözleşmesi**  
Kapsam: GitHub-only, salt-okunur çekirdek

## 1. Amaç

Sistem, Tokenoskobi ve Quant Simulator repository'lerinin sürümlü ihtiyaç profilini
çıkarır; GitHub üzerindeki yeni veya değişen adayları artımlı biçimde toplar ve
yalnız kanıta dayalı araştırma kararı üretir.

MVP kod çalıştırmaz, paket kurmaz, branch/commit/PR oluşturmaz ve uygulama kararı
vermez.

## 2. Değişmez kurallar

1. `impact_score` ve `confidence_score` ayrıdır; tek puanda birleştirilmez.
2. Her skor deterministik formül, ölçüm veya açık veriyle açıklanır.
3. Dış kaynak içeriği güvenilmeyen veridir ve talimat olarak uygulanmaz.
4. Sistem salt-okunurdur.
5. Kritik politika kapısı başarısızsa pahalı analiz çalıştırılmaz.
6. İş teslimi at-least-once, sonuç kaydı idempotenttir.
7. Olay geçmişi append-only; güncel durum materialized state'tir.
8. Olay, güncel durum ve idempotency kaydı tek transaction içinde yazılır.
9. Boş günlük rapor başarılı sonuçtur.
10. Bütçe aşımındaki adaylar silinmez; kuyruğa taşınır.

## 3. Kapsam

### Dahil

- İki repo için salt-okunur snapshot
- dosya, dependency, import ve test ilişkileri
- değişiklik ve etki alanı kayıtları
- sürümlü Need Graph
- GitHub baseline ve artımlı discovery modeli
- cursor/checkpoint/overlap
- source/content/analysis kimlikleri
- politika kapıları, kanıt, impact ve confidence
- araştırma kararı
- SQLite event log ve günlük Markdown rapor
- kullanıcı geri bildirimi ve dependency-health kayıtları

### Hariç

- YouTube ve transcript
- otomatik PoC veya paket kurulumu
- uygulama/integrasyon kararı
- repository değişikliği veya PR
- makine öğrenmesi ve dağıtık worker
- grafik veritabanı

## 4. İşlem hattı

```text
DISCOVER → FETCH → NORMALIZE → DEDUPLICATE → PREFILTER
→ ENRICH → POLICY GATES → ANALYZE → ASSESS → RESEARCH DECISION → REPORT
```

Her aday bağımsız ilerler. Bir adayın hatası diğer adayların işlenmesini durdurmaz.

## 5. Kimlik sözleşmesi

```text
SOURCE_KEY   = sha256(provider + NUL + native_id)
CONTENT_KEY  = sha256(normalized_content_utf8)
ANALYSIS_KEY = sha256(content_key + NUL + repository_snapshot_id + NUL
                      + need_profile_version + NUL + scoring_policy_version
                      + NUL + analysis_version)
JOB_KEY      = sha256(candidate_id + NUL + operation_type + NUL
                      + input_version + NUL + worker_version)
```

Hash girdileri UTF-8 kodlanır. Metin normalize edilirken satır sonları `LF` yapılır;
baş/son boşlukları kaldırılır. Kaynağa özgü anlamsız alanlar normalize edici
sürümü tarafından açıkça tanımlanır.

## 6. Politika kapıları

Kesin sıra:

1. `UNTRUSTED_CONTENT`
2. `LICENSE`
3. `AUTHORITY_SECRET_PRIVATE_KEY`
4. `SUPPLY_CHAIN`
5. `BASIC_REPOSITORY_FIT`
6. `EVIDENCE_SUFFICIENCY`
7. impact assessment
8. confidence assessment
9. research decision

Kapı sonucu `PASS`, `BLOCK`, `DEFER` veya `NOT_EVALUATED` olabilir. `BLOCK`, girdi
değişene kadar sonraki pahalı aşamaları durdurur; kaynak ve gerekçe korunur.

## 7. Değerlendirme sözleşmesi

Her boyut (`speed`, `capability`, `security`, `economy`, `repository_fit`) ayrı
değerlendirilir.

```yaml
dimension: security
impact_score: 82
confidence_score: 46
evidence_level: external_benchmark
applicability: uncertain
formula_id: security-impact-v1
policy_version: assessment-policy-v1
input_evidence_ids: [evidence-104, evidence-109]
```

Skor aralığı 0–100'dür. Skor yoksa `NULL` kullanılır; kanıtsız değere sıfır verilmez.
Karar motoru iki skoru birleştirerek sahte kesinlik üretmez.

Araştırma kararları:

- `IGNORE`
- `WATCH`
- `INVESTIGATE`
- `URGENT_INVESTIGATION`

## 8. Durum ve transaction invariantı

Durumlar:

```text
DISCOVERED, FETCH_PENDING, FETCHED, NORMALIZED, DEDUPLICATED,
PREFILTERED, ENRICHMENT_PENDING, ENRICHED, ANALYSIS_PENDING,
ANALYZED, MEASUREMENT_PENDING, MEASURED, REVIEW_REQUIRED,
BLOCKED, REPORTED, RETRYABLE_ERROR, TERMINAL_ERROR
```

Durum geçişi aynı transaction içinde şunları yapar:

```text
INSERT candidate_events
UPDATE candidates.current_status
INSERT idempotency_records
COMMIT
```

Herhangi biri başarısızsa transaction rollback edilir. Event satırları UPDATE veya
DELETE edilemez.

## 9. Checkpoint invariantı

```text
NEXT_SCAN_FROM = LAST_SUCCESSFUL_CHECKPOINT - OVERLAP_WINDOW
```

Checkpoint yalnız başarıyla kalıcılaştırılmış kayıtların sonrasına ilerletilir.
Kısmi başarıda kaydedilemeyen aralık checkpoint'in gerisinde bırakılır.

## 10. Hata ve yeniden deneme

| Tür | Davranış |
|---|---|
| transient | en fazla 5, exponential backoff |
| rate limit | sağlayıcı penceresinden sonra yeniden dene |
| authentication | kaynağı duraklat ve uyar |
| malformed content | terminal error |
| transcript unavailable | gelecekteki değişikliği izle |
| budget exhausted | carry forward |
| policy block | girdi değişene kadar blok |

## 11. Gizli bilgi sınırı

```text
repository content → secret scan → sensitive path classification
→ minimum context → deterministic redaction → model policy gate → analysis
```

`.env`, private key, token, credential, wallet seed, müşteri verisi, özel RPC
kimliği, üretim sırrı ve maskelenmemiş iç endpoint dış modele gönderilemez.

## 12. Kabul ölçütleri

- duplicate analysis rate `< 1%`
- missed checkpoint items `0`
- unexplained decisions `0`
- forced daily findings `0`
- event/state divergence `0`
- policy gate bypass `0`

Kuzey yıldızı:

```text
TOTAL_RADAR_COST / HUMAN_VERIFIED_USEFUL_CANDIDATE_COUNT
```

Payda yalnız `human_useful=true`, maddi kanıtı bulunan, açıklanmış ve duplicate
olmayan adayları içerir.
