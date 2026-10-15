# Willis Label – Adım adım kullanım kılavuzu

Örnek veri: IXI013-HH-1212-MRA (IXI veri seti, CC BY-SA 3.0, https://brain-development.org/ixi-dataset/).
Slicer sürümü: 3D Slicer 5.12.3.

> Geliştirme sürümü. Modül henüz Extension Manager'da yok, bu yüzden klasör olarak elle ekleniyor (Adım 1).

---

## Adım 1 – Modül yolunu ekleyin (yalnızca bir kez)

**Edit → Application Settings → Modules** bölümüne gidin. **Additional module paths** kutusunun sağındaki **»** düğmesine basın, ardından **Add**'e basın.

Açılan pencerede dıştaki `SlicerWillisLabel` klasörünü değil, onun **içindeki `WillisLabel` klasörünü** seçin. Doğru klasörün içinde `WillisLabel.py` dosyası ve `WillisLabelLib` klasörü bulunur. Örnek:

`C:\Users\LENOVO\Desktop\eda_yilmaz_TOF-flair\SlicerWillisLabel\WillisLabel`

**OK** deyip Slicer'ı kapatıp yeniden açın.

> Klasörü daha sonra başka bir yere taşırsanız bu yolu da güncellemeniz gerekir. Eski yol listede kalırsa Slicer modülü bulamaz ya da eski kopyayı yükler.

Listenin en altında `.../SlicerWillisLabel/WillisLabel` satırı görünmelidir:

![Modül yolu](01_modul_yolu.png)

## Adım 2 – TOF-MRA görüntüsünü açın

**File → Add Data** (ya da sürükle-bırak) ile TOF görüntüsünü yükleyin (`.nii.gz`, `.nrrd` ya da DICOM).

![Veri yüklendi](02_veri_yuklendi.png)

## Adım 3 – Modülü açın

Araç çubuğundaki **büyüteç** simgesine tıklayın, **Willis** yazın ve **Switch to module**'e basın. Modül, *Segmentation* kategorisinde **Willis Label** adıyla da bulunabilir.

Panelde dört bölüm vardır: *1. Extract arteries*, *2. Place seeds*, *3. Label arteries* ve *4. Export*.

![Modül paneli](03_modul_paneli.png)

## Adım 4 – Arterleri çıkarın

*TOF volume* kutusunda görüntünüz seçili olmalı. Eşik değerleri otomatik olarak önerilir: bu olguda **Low 911 / High 1335**. **Extract arteries**'e basın. Birkaç saniye içinde damar ağacı kesitlerde kırmızı olarak görünür ve *Artery mask* kutusuna `Arteries mask` gelir.

![Arterler çıkarıldı](04_arterler_cikarildi.png)

**Dikkat:** TOF'ta yağ dokusu da parlak görünür. Orbita yağı ve kafa derisi maskeye girebilir. Gerekirse *Segment Editor*'de silebilirsiniz.

## Adım 5 – 3B görünümü hazırlayın

Willis halkası en iyi alttan (**inferior**) görünür. 3B pencerenin üst şeridindeki **raptiye (📌)** simgesine tıklayın, yön düğmelerinden **I**'yı seçin ve fare tekerleğiyle yakınlaşın. Bu görünümde üst taraf anteriordur ve **ekranın solu hastanın sağıdır**.

## Adım 6 – Tohum noktalarını yerleştirin

1. **Artery** listesinden arteri seçin (örneğin `BA – A. basilaris`). Liste açıkken kısaltmayı yazmak (`ICA R`, `P1 L`…) doğrudan o satıra götürür.
2. **Place**'e basın ve 3B görünümde (ya da kesitte) o arterin üzerine tıklayın. Nokta, seçili arterin adını otomatik olarak alır.
3. Listeden sıradaki arteri seçip tıklamaya devam edin. Yerleştirme modu açık kalır, her seferinde Place'e basmanız gerekmez.
4. Görünmeyen arterleri atlayın. Bitince **Esc**'ye basın.

Tablodaki **R** sütunundan tarafı kontrol edin: **pozitif = sağ, negatif = sol**. Yanlış adlandırılmış bir noktayı tablodaki adına çift tıklayarak düzeltebilirsiniz.

Bu örnekte 12 nokta yerleştirildi: BA, ICA R/L, MCA R/L, A1 R, AComA, A2 L, P1 R/L, P2 R/L.

![Tohum noktaları](05_tohumlar.png)

## Adım 7 – Etiketleyin

**3. Label arteries** bölümünde **Label arteries**'e basın. Her arter Latince adı ve kendi rengiyle ayrı bir segment olur. Alttaki kutuda her arterin hacmi (mm³) ve tohum konmamış arterlerin listesi yazar.

![Etiketli sonuç](06_etiketli_sonuc.png)

![Etiketli sonuç – dörtlü görünüm](07_etiketli_dortlu.png)

## Adım 8 – Dışa aktarın (3B baskı için)

**4. Export** bölümünde bir klasör seçin ve **Export each artery as STL**'e basın. Her arter ayrı bir STL dosyası olarak kaydedilir.

---

## Bu örnekte görülen sınırlamalar (geliştirme notu)

Yukarıdaki sonuç bir **iş akışı gösterimi**dir; etiketler anatomik olarak tamamen doğru değildir:

- **Tohum konmamış dallar en yakın tohumun adını alıyor.** PComA, SCA, AChA, oftalmik arter ve kortikal dallar ayrı tohum almadığı için komşu bir arterin rengine boyanıyor. Örneğin turuncu *AComA* segmenti fazla büyük (1973 mm³).
- **Orbita yağı bir artere bağlanıyor.** Sağdaki yağ ICA R'ye, soldaki MCA L'ye katılmış (ICA R 5097 mm³, MCA L 7312 mm³).
- **İki A2 alttan bakınca üst üste biniyor.** A2'leri ve A1 L'yi koronal kesitte işaretlemek daha doğru olur.

Planlanan iyileştirmeler:

1. Tohumsuz dalları "*X'in diğer dalları*" olarak ayrı göstermek.
2. Yağ dokusunu biçim (tübülerlik) ölçütüyle ayıklamak.
3. Tohumları kesit görüntüsünde de kolay yerleştirmek.
