# 📱 AppVault — اكتشف أفضل تطبيقات الهاتف يومياً

منصة عربية Full‑Stack لاكتشاف وإدارة أفضل تطبيقات الهاتف، مبنية بقاعدة بيانات SQLite وواجهة إدارة آمنة.

## 🔗 الموقع
**[https://ayoub5550.github.io/AppVault/](https://ayoub5550.github.io/AppVault/)**

## ✨ المميزات
- 🔍 بحث سريع عن التطبيقات
- 🏷️ تصنيف حسب الفئات (AI, إنتاجية, أدوات, موسيقى...)
- 📲 فلترة حسب المنصة وترتيب حسب الأحدث أو التقييم أو الاسم
- ♿ تجربة محسّنة لقارئات الشاشة ولوحة المفاتيح
- 🤖 يُحدَّث تلقائياً بواسطة AI
- 📱 متجاوب مع الهاتف والكمبيوتر
- 🌙 تصميم داكن أنيق

## 📦 كيف يعمل
1. يخزن التطبيقات والتقييمات والإحصاءات في قاعدة SQLite.
2. يعرض API للبحث والفلترة والترتيب وقياس النقرات.
3. تتيح لوحة الإدارة إضافة التطبيقات وتعديلها ونشرها دون تحرير ملفات JSON.
4. يُستخدم `apps.json` مرة واحدة فقط لاستيراد البيانات الأولية.

## 📁 الملفات
- `index.html` — الموقع الرئيسي
- `apps.json` — قاعدة بيانات التطبيقات
- `scripts/validate_apps.py` — يتحقق من صحة البيانات قبل النشر

## ✅ التحقق محلياً
```bash
python scripts/validate_apps.py apps.json
```

شغّل هذا الفحص قبل كل تحديث لملف البيانات للتأكد من الحقول والروابط والمعرّفات.

## استيراد البيانات الأولية
لاستيراد تطبيق جديد عند إنشاء قاعدة بيانات جديدة، أضف كائن JSON في `apps.json`:
```json
{
    "id": 16,
    "name": "App Name",
    "name_ar": "اسم التطبيق",
    "category": "ai|productivity|tools|music|weather|social",
    "category_ar": "الفئة بالعربية",
    "description": "English description",
    "description_ar": "الوصف بالعربية",
    "platform": "android|ios|both",
    "rating": 4.5,
    "price": "free|freemium|paid",
    "url": "https://play.google.com/...",
    "image": "",
    "added_date": "2026-05-27",
    "tags": ["tag1", "tag2"]
}
```

---
*مدعوم بالذكاء الاصطناعي © 2026 Ayoub*


## تشغيل النسخة Full‑Stack
```bash
export APPVAULT_ADMIN_USER=admin
export APPVAULT_ADMIN_PASSWORD='change-me'
python server.py
```
ثم افتح الموقع على `http://127.0.0.1:8080` ولوحة الإدارة على `/admin`.

> في الإنتاج شغّل الخدمة خلف Caddy أو Nginx، واحفظ كلمات المرور في ملف بيئة بصلاحيات مقيدة.
