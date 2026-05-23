# LibraryMS

نظام إدارة مكتبة ورقية ورقمية مبني باستخدام Django.

## تشغيل المشروع لأول مرة

1. ثبت المتطلبات:

```bash
pip install -r requirements.txt
```

2. أنشئ ملف `.env` في جذر المشروع عند الحاجة، ثم شغّل الترحيلات:

```bash
python manage.py migrate
```

عند تشغيل الترحيلات لأول مرة على قاعدة بيانات فارغة يتم إنشاء حساب المدير الأول تلقائيا برقم `1` في قاعدة البيانات، ويملك كل الصلاحيات.

بيانات الدخول الافتراضية:

- اسم المستخدم: `admin`
- كلمة المرور: `Admin@12345`
- البريد: `admin@example.com`

يمكن تغيير هذه القيم قبل أول تشغيل عبر متغيرات البيئة:

```env
INITIAL_ADMIN_USERNAME=admin
INITIAL_ADMIN_PASSWORD=Admin@12345
INITIAL_ADMIN_EMAIL=admin@example.com
```

بعد تسجيل الدخول افتح صفحة **حسابي الإداري** لتغيير اسم المستخدم وكلمة المرور والبريد. المدير رقم `1` فقط يستطيع تعديل إعدادات النظام العامة.

## إعدادات الغرامة والحجز والاستعارة

من صفحة **حسابي الإداري** يستطيع المدير رقم `1` تعديل:

- مبلغ الغرامة لكل يوم تأخير.
- عدد أيام الحجز.
- عدد أيام الاستعارة.
- حساب البريد المستخدم لإرسال رسائل الأعضاء ورسائل التحقق.

القيم الافتراضية يمكن ضبطها أيضا من ملف `.env`:

```env
LIBRARY_FINE_PER_UNIT=1000
LIBRARY_RESERVATION_DAYS=2
LIBRARY_BORROW_DAYS=3
LIBRARY_DEMO_MODE=0
```

إذا جعلت `LIBRARY_DEMO_MODE=1` فسيستخدم النظام مدد قصيرة بالدقائق للتجربة السريعة.

## متغيرات البريد الإلكتروني

لا تشارك ملف `.env` إذا كان يحتوي على بريدك الشخصي أو كلمة مرور التطبيق. عند نقل المشروع، عرّف هذه المتغيرات أو اتركها فارغة ثم اضبط البريد من صفحة **حسابي الإداري** بواسطة المدير رقم `1`.

```env
EMAIL_USER=your-email@gmail.com
EMAIL_PASS=your-app-password
DEFAULT_FROM_EMAIL=your-email@gmail.com
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_USE_SSL=0
ADMIN_MANAGER_EMAIL=admin@example.com
EMAIL_OTP_TTL_SECONDS=300
ADMIN_RESET_CODE_TTL_SECONDS=300
```

لخدمة Gmail يجب استخدام **كلمة مرور تطبيق** وليس كلمة مرور الحساب العادية.

## متغيرات أساسية أخرى

```env
DJANGO_SECRET_KEY=change-this-secret-key
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*
DJANGO_CSRF_TRUSTED_ORIGINS=
DATABASE_URL=
```

إذا لم يتم تعريف `DATABASE_URL` سيستخدم المشروع قاعدة SQLite المحلية `db.sqlite3`.
