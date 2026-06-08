# 🚀 CopyTrading Backend - Setup Guide
## Alice Blue Real Copy Trading

---

## 📋 STEP 1: Files Download Karo
Ye saari files ek folder mein rakho:
- main.py
- alice_blue.py
- copy_engine.py
- database.py
- models.py
- auth.py
- requirements.txt
- railway.json

---

## 📋 STEP 2: GitHub pe Upload Karo

1. **github.com** pe jaao → Account banao (free)
2. "New Repository" click karo
3. Name: `copytrading-backend`
4. Public select karo → Create
5. "uploading an existing file" click karo
6. Saari files drag & drop karo
7. "Commit changes" click karo

---

## 📋 STEP 3: Railway pe Deploy Karo

1. **railway.app** pe jaao → GitHub se login karo
2. "New Project" → "Deploy from GitHub repo"
3. `copytrading-backend` select karo
4. Deploy automatically shuru ho jaayega ✅

---

## 📋 STEP 4: Environment Variables Set Karo

Railway dashboard mein "Variables" tab mein jaao aur ye add karo:

```
SECRET_KEY = koi_bhi_random_string_likho_yahan_123xyz
ENCRYPT_KEY = (Railway khud generate kar dega, ya https://fernetkeygen.com se lo)
```

---

## 📋 STEP 5: Backend URL Lo

Railway deploy hone ke baad ek URL milegi jaise:
`https://copytrading-backend-production.up.railway.app`

Ye URL apne frontend (React app) mein add karo.

---

## ✅ Test Karo

Browser mein ye URLs open karo:

- `YOUR_URL/` → "CopyTrading API is live!" dikhna chahiye
- `YOUR_URL/docs` → Poori API documentation dikhegi (Swagger UI)

---

## 🔄 Kaise Kaam Karta Hai?

```
Aap Master Account connect karo
         ↓
Backend har 2 second mein aapka trade book check karta hai
         ↓
Naya trade detect hota hai
         ↓
Automatically saare active child accounts mein copy hota hai
         ↓
Database mein log save hota hai
```

---

## ⚠️ Important Notes

1. **Alice Blue API Key** real hona chahiye (antbroking.in se)
2. **Market hours** mein hi kaam karega (9:15 AM - 3:30 PM)
3. **Margin** child accounts mein hona chahiye trade copy ke liye
4. SEBI rules follow karo

---

## 🆘 Problem Aaye Toh?

Railway dashboard mein "Logs" tab dekho — wahan sab kuch dikhega.
