# 📱 AppVault — اكتشف أفضل تطبيقات الهاتف يومياً

موقع يُحدَّث تلقائياً بواسطة Tony AI Agent لاكتشاف أحدث تطبيقات الهاتف.

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
1. Tony AI Agent يبحث عن تطبيقات جديدة كل فترة
2. يضيفها إلى `apps.json`
3. يرفع التحديث إلى GitHub
4. الموقع يتحدث تلقائياً عبر GitHub Pages

## 📁 الملفات
- `index.html` — الموقع الرئيسي
- `apps.json` — قاعدة بيانات التطبيقات
- `scripts/validate_apps.py` — يتحقق من صحة البيانات قبل النشر

## ✅ التحقق محلياً
```bash
python scripts/validate_apps.py apps.json
```

شغّل هذا الفحص قبل كل تحديث لملف البيانات للتأكد من الحقول والروابط والمعرّفات.

## 🤖 للعميل (Tony)
لإضافة تطبيق جديد، أضف كائن JSON في `apps.json`:
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
