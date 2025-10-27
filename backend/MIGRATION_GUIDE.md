# Migration Rehberi

Bu rehber, veri modeli değişikliklerinden sonra Alembic ile çalışırken izlenmesi gereken adımları ve temiz kurulum yönergelerini içerir.

## Model Değişikliği Sonrası Adımlar

1. **Revizyon oluşturma (autogenerate):**
   ```bash
   alembic revision --autogenerate -m "Açıklayıcı bir mesaj"
   ```
   * Alembic, `app/` altındaki modellerdeki değişiklikleri algılar ve yeni bir revizyon dosyası üretir.
   * Otomatik üretimin eksik kalabileceğini unutmayın; özellikle karmaşık SQL ifadeleri elle eklenmelidir.

2. **Revizyon dosyasını kontrol etme:**
   * `alembic/versions/` altında oluşan dosyayı açarak `upgrade()` ve `downgrade()` fonksiyonlarının beklenen işlemleri içerdiğinden emin olun.
   * SQLite kullanırken tablolar üzerinde değişiklik yapmanız gerekiyorsa `op.batch_alter_table` kullanmaya dikkat edin; bu sayede "batch mode" etkinleşir ve ALTER komutlarının kısıtları aşılır.

3. **Migrasyonları test etme (upgrade/downgrade):**
   ```bash
   alembic upgrade head
   alembic downgrade -1
   alembic upgrade head
   ```
   * `upgrade head` komutu en son revizyona kadar yükseltir.
   * `downgrade -1` bir önceki revizyona geri döner; geri dönüşlerin çalıştığını doğrulamak için kullanılır.
   * Testler sırasında veri kaybını önlemek için yerel geliştirme veritabanı üzerinde çalıştığınızdan emin olun.

4. **Commit mesajı:**
   * Onayladığınız revizyon dosyasını diğer kod değişiklikleriyle birlikte commit'leyin.
   * Commit mesajında migrasyonun amacını belirtin (örn. `Add user profile table migration`).

## Temiz Kurulum Yönergeleri

Yeni bir kurulumda veritabanını güncel tutmak için aşağıdaki adımları izleyin:

1. Gerekirse mevcut veritabanı dosyasını kaldırın veya temiz bir veritabanı oluşturun.
2. Ortam değişkenlerini ve konfigürasyonu (`alembic.ini`) doğru ayarladığınızdan emin olun.
3. Tüm tablolara ulaşmak için migrasyonları çalıştırın:
   ```bash
   alembic upgrade head
   ```
4. Geliştirme ortamında testleri veya örnek verileri yükleyin.

## Alembic Komutları Hızlı Referansı

| Komut | Açıklama |
| --- | --- |
| `alembic revision --autogenerate -m "mesaj"` | Model değişikliklerinden yeni bir revizyon oluşturur. |
| `alembic upgrade <hedef>` | Migrasyonları belirtilen revizyona kadar uygular (`head` en güncel sürümdür). |
| `alembic downgrade <hedef>` | Migrasyonları belirtilen revizyona geri alır (`-1` bir önceki revizyon). |
| `alembic history --verbose` | Tüm revizyon geçmişini detaylarıyla listeler. |
| `alembic current` | Veritabanının şu an hangi revizyonda olduğunu gösterir. |

### Dikkat Edilmesi Gerekenler

* SQLite üzerinde ALTER işlemleri sınırlıdır; Alembic yapılandırmasında `render_as_batch=True` ayarını etkin tutun veya revizyonlarda `op.batch_alter_table` kullanın.
* Üretim veritabanlarında downgrade işlemleri veri kaybına yol açabilir; gerekli yedekleri almadan downgrade yapmayın.
* Otomatik üretilen revizyonu manuel olarak düzenlerken import'ları ve bağımlılıkları bozmadığınızdan emin olun.

