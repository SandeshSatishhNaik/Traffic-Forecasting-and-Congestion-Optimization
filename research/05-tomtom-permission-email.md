# Email to TomTom: permission to store results for academic research

Why: TomTom's Maps API terms restrict storing results (11.4), building derived databases (11.6.1) and using results in machine-learning data sets (11.6.4), and "Evaluation Use" is defined as internal evaluation and testing (details in `04-road-network-and-factors.md`, section 4). Written permission is the only thing that removes the conflict. This email asks for it.

How to send it: from your own email address, through TomTom's contact form (<https://www.tomtom.com/contact-sales/>) or the support option in your developer portal at <https://my.tomtom.com>. Fill in every [bracket] first. Ask your mentor to be copied; a request from a supervised student project is taken more seriously. Send it once the private repository is in use, so that the sentence about the public copy is true.

TomTom may answer with a paid product (for example historical Traffic Stats) or a refusal. A refusal is still useful for the report: it tells the evaluators why the Bengaluru data stays private, and the METR-LA / PEMS-BAY benchmarks carry the published results.

---

**Subject:** Request for written permission: academic research use of Traffic Flow and Incidents API results (student project, Bengaluru)

Hello TomTom team,

I am a student at [college / university], working under [mentor name, mentor email] on a project called "AI-Driven Spatio-Temporal Traffic Intelligence System for Traffic Forecasting and Congestion Optimization". We study short-term traffic forecasting on a corridor in Bengaluru, India: the Outer Ring Road between Silk Board and KR Puram, and the roads that feed it.

**What we do today**

- We call the Traffic Flow Segment Data API for about [20] road stretches and the Traffic Incident Details API for one bounding box, every 15 to 60 minutes.
- We stay inside the free monthly allowance (20,000 and 2,500 requests). We use the API key from my own developer account.
- We append the responses to CSV files and use them offline to train and test forecasting models.
- There is no commercial use, no resale and no end-user product.

**Why I am writing**

Your terms (sections 11.4, 11.6.1 and 11.6.4) restrict storing results, creating derived databases and using results in machine-learning data sets, and "Evaluation Use" is defined as internal evaluation and testing. I did not read those sections closely at first. For about [three days, from 27 to 30 September 2026] a copy of the responses sat in a public GitHub repository. [I have moved it to a private repository and removed the public copy. Edit this sentence so it is true when you send it.]

**What I am asking permission for**, limited to this study ([start date] to [end date, about 8 to 12 weeks]):

1. Store the API responses in a private, access-controlled repository for the length of the study, and delete them within [30] days after the study ends (or keep them for the evaluation until [date]).
2. Use the stored responses to train and evaluate forecasting models for academic research.
3. Publish aggregated results only (accuracy numbers, charts, example forecasts) in the project report, crediting TomTom as the data source. We would not publish or share the raw responses or a dataset.
4. Show the raw data privately to the project mentors and evaluators if they ask, under the same conditions.

**Questions**

- Is there an academic or research programme, or a historical traffic dataset offered for research, that would suit this project better than the public API?
- If this request belongs with another team, could you point me to them?

Thank you for your time. I can send the project description or a letter from my mentor if that helps.

Regards,
[your name]
[college, course, year]
[email]
[TomTom developer account email (not the API key)]

---

Never put the API key in the email.
