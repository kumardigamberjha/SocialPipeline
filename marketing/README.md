# 🎯 Wings of AI — Marketing & Growth Suite

Welcome to the **Wings of AI Marketing Hub**. This folder contains targeted lead datasets, automated prospecting tools, and high-conversion cold outreach campaigns engineered specifically to sell the Wings of AI platform to YouTubers, DevRel teams, and digital media agencies.

---

## 📁 Directory Structure

```
marketing/
├── README.md                            # Marketing hub guide and operational workflows
├── youtube_business_leads_1000.csv      # 1,000 verified creator & business leads with direct emails
├── lead_finder.py                       # Automated Google / DuckDuckGo / YouTube search & scraper tool
├── send_outreach.py                     # Anti-bot compliant cold outreach dispatcher
├── outreach_sent_log.csv                # Real-time delivery audit log with Message-IDs
└── outreach_campaign_playbook.md        # Plug-and-play cold email sequences mapped to CSV variables
```

---

## 📊 Leads Database: `youtube_business_leads_1000.csv`

The database contains **1,000 highly qualified leads** partitioned across 5 core high-intent customer segments:

| Category | Lead Count | Key Persona | Estimated Tier |
| :--- | :---: | :--- | :--- |
| **AI & Machine Learning Creators** | 250 | Prominent & rising AI/ML educators | Pro Creator ($79/mo) |
| **Web & Full-Stack Development Creators** | 250 | Web dev, Next.js, and JS creators | Pro Creator ($79/mo) |
| **B2B DevTool & SaaS Founders** | 200 | Open core & developer tool founders | Enterprise DevRel ($499+/mo) |
| **Cloud, DevOps & Systems Creators** | 150 | Kubernetes, Cloud & Architecture leads | Pro Creator ($79/mo) |
| **Digital Media & Growth Agencies** | 150 | YouTube growth studios & consultancies | Agency Pro ($199/mo) |
| **Total** | **1,000** | | |

### CSV Columns:
- `lead_id`: Sequential record ID (1 to 1000).
- `name`: Contact person (creator, founder, or partner).
- `channel_or_company`: Channel brand or company name.
- `category`: Target segment name.
- `business_email`: Clean, verified business inquiry email.
- `channel_url_or_website`: Link to YouTube channel or official domain.
- `audience_size`: Subscriber count (e.g., `450K Subscribers`) or team size.
- `primary_niche`: Focused topic area.
- `country`: Location/geography hub.
- `primary_pain_point`: Immediate content bottleneck Wings of AI resolves.
- `personalized_pitch_hook`: Pre-crafted opening line customized for cold email.
- `product_fit_score`: Objective fit score out of 10.
- `estimated_tier`: Recommended pricing tier.
- `outreach_status`: Pipeline tracking status (`Ready for Outreach`).

---

## 🚀 Running the Automated Lead Prospector (`lead_finder.py`)

The included prospecting script can discover and enrich additional leads dynamically:

### 1. Audit Existing Leads
```bash
python3 marketing/lead_finder.py --audit
```

### 2. Search & Extract New Leads for a Specific Tech Niche
```bash
python3 marketing/lead_finder.py \
  --query "Next.js 15 YouTube tutorials" \
  --category "Web & Full-Stack Development Creator" \
  --niche "Next.js 15 & React Server Components" \
  --count 10
```

### 3. Target B2B SaaS Founders & DevRel Teams
```bash
python3 marketing/lead_finder.py \
  --query "AI developer tools site:github.com OR site:youtube.com" \
  --category "B2B DevTool & SaaS Founder" \
  --niche "Developer APIs & LLM Frameworks" \
  --count 15
```

---

## 📬 Executing Cold Email Outreach

1. Open [`outreach_campaign_playbook.md`](file:///media/digamber-jha/G13/MyEmpire/Content%20Creator/marketing/outreach_campaign_playbook.md) for pre-written email sequences.
2. Import `youtube_business_leads_1000.csv` into your cold email software (Instantly, Smartlead, Apollo, or Lemlist).
3. The custom fields map 1:1 with email variables:
   - `{{name}}`
   - `{{channel_or_company}}`
   - `{{personalized_pitch_hook}}`
   - `{{primary_niche}}`
   - `{{primary_pain_point}}`
4. Set sending caps to 30–45 emails/day per sender address to maintain stellar inbox deliverability.
