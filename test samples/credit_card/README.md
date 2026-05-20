# Credit card statement PDFs (6 months)

Demo uploads for SmartSpend **`source_type: credit_card`**.

| Person | File | Period | ~Transactions |
|--------|------|--------|----------------|
| **Chirag Solanki** | `HDFC_CREDIT_CARD_STATEMENT_Chirag_Solanki.pdf` | 01 Dec 2025 – 14 May 2026 | ~150+ |
| **Amruta Abhangrao** | `ICICI_CREDIT_CARD_STATEMENT_Amruta_Abhangrao.pdf` | 01 Dec 2025 – 14 May 2026 | ~150+ |

## Included spend types

- **Flights:** IndiGo, Air India, MakeMyTrip, Goibibo  
- **Hotels:** OYO, Marriott, Booking.com, Taj, FabHotels  
- **Trains:** IRCTC, ConfirmTkt  
- **EMIs on card:** iPhone / MacBook (Chirag), Sony / Samsung Tab (Amruta)  
- **AI & work:** ChatGPT Plus, Cursor, GitHub, Notion, Adobe  
- **Subscriptions:** Netflix, Spotify, LinkedIn, Prime, Hotstar, etc.  
- **Daily:** Swiggy, Zomato, Amazon, fuel, shopping  

## Upload

1. Login as Chirag or Amruta  
2. Credit card source → upload matching PDF  
3. Institution: **HDFC Regalia** or **ICICI Coral**

## Regenerate

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\generate_team_credit_card_pdfs.py
```
