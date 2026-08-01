# HubTube — GitHub-only Technology Benefit Radar

HubTube, Tokenoskobi ve Quant Simulator için salt-okunur, artımlı teknoloji radarı
çekirdeğidir. İsim, GitHub keşfini ve ileride eklenecek YouTube katmanını birleştirir.

Bu sürüm mimari sözleşmeyi dondurur ve aşağıdaki temelleri sağlar:

- SQLite şeması ve append-only olay geçmişi
- aday durumu + olay geçmişinin tek transaction içinde güncellenmesi
- idempotent iş sonucu kaydı
- source/content/analysis kimlikleri
- checkpoint ve overlap modeli
- politika kapıları için kayıt modeli
- impact ve confidence skorlarının ayrı tutulması
- boş sonuçları da destekleyen günlük Markdown raporu
- salt-okunur Repository Observer v1

## Hızlı başlangıç

Python 3.11 veya üzeri yeterlidir; harici paket gerekmez.

```powershell
python -m radar --db work/radar.db init
python -m radar --db work/radar.db self-test
python -m radar --db work/radar.db report --date 2026-08-01 --output work/daily-report.md
python -m radar --db work\radar.db observe C:\path\to\repository `
  --repo-key tokenoskobi --full-name anketci54-coder/tokenoskobi `
  --output work\snapshot.json
```

Observer yalnız dosya okur; kod çalıştırmaz ve paket kurmaz. `.git`, `work/`, sanal ortamlar,
`node_modules` ve cache dizinlerini atlar. Dosya hash'leri, sınıflandırma, hassas dosya
işaretleri ve Python import ilişkileri üretir. Hassas dosyaların içeriği çıktıya yazılmaz.
Snapshot SQLite'a kaydedilir; sonraki çalışmada yalnız eklenen, değiştirilen veya silinen
dosyalar sınıflandırılır ve bunlara bağlı etki bağlamı raporlanır. Aynı snapshot yeniden
gözlemlenirse `REPO_CHANGED=false` üretilir.

## Need Graph v1

Observer snapshot'ından deterministik ve kanıtlı ihtiyaç önerileri üretin:

```powershell
python -m radar --db work\radar.db needs propose --repo-key tokenoskobi
python -m radar --db work\radar.db needs approve PROPOSAL_ID --approved-by anketci54-coder
python -m radar --db work\radar.db needs list --repo-key tokenoskobi
```

Öneriler otomatik olarak aktifleşmez. Her ihtiyaç insan onayı, kaynak snapshot kimliği,
deterministik kural ve kanıt kaydı taşır. Kritik ihtiyaçlar sonraki sürümlerde sessizce
silinemez veya otomatik olarak düşük önceliğe indirilemez.

Gerçek GitHub taramasından önce `config.example.toml` dosyasını `config.toml` olarak
kopyalayın ve iki repository değerini doldurun. Token gerekiyorsa yalnız ortam
değişkeninden verilmelidir; yapılandırma veya veritabanına yazılmamalıdır.

```powershell
$env:RADAR_GITHUB_TOKEN = "..."
python -m radar --db work/radar.db scan-github --config config.toml
```

`scan-github` bu başlangıç sürümünde bilinçli olarak devre dışıdır; repo adresleri
doğrulandıktan sonra GitHub istemcisi eklenmelidir. Hiçbir komut hedef repolara yazmaz.

## Belgeler

- `docs/TECHNICAL_SPEC_v1.md`: dondurulmuş uygulama sözleşmesi
- `schema/001_initial.sql`: SQLite veri modeli ve invariant trigger'ları
- `config.example.toml`: çalışma politikası örneği

## Lisans

MIT
