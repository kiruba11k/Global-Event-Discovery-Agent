/*
  faqData.js - single source of truth for the FAQ page (FaqPage.jsx).
  The JSON-LD FAQPage schema is generated straight from this data so the
  schema and the visible page copy can never drift out of sync - if you
  edit an answer here, the schema updates with it automatically.

  Five questions (marked NEEDS_INPUT below) publish only their safe first
  paragraph - the original brief's second paragraph for each depended on
  a business-policy decision (no-show policy, sending setup, etc.) that
  only LeadStrategus can confirm. Nothing is fabricated; ping the person
  who asked for this page for those five answers and extend the
  `paragraphs` array once confirmed.
*/

export const FAQ_CATEGORIES = [
  {
    id: 'what-expotofunnel-does',
    heading: 'What ExpoToFunnel does',
    questions: [
      {
        id: 'what-is-expotofunnel',
        q: 'What is ExpoToFunnel?',
        paragraphs: [
          'ExpoToFunnel is a B2B trade show pipeline-build platform. It ranks 17,007 indexed trade shows across 129 countries by how densely your ideal customers attend each one, then books qualified meetings with matched attendees before the event and gives you a talking points brief for every meeting',
          'The ranking is free and instant. The meeting booking and the briefs are delivered by our team when you engage us on a paid package.',
          'ExpoToFunnel is built and run by LeadStrategus, a B2B demand generation and go-to-market consulting firm setting up B2B meetings across the world using local idioms and deep, human-led research and personalisation.',
        ],
      
        related: { label: 'See how it works', href: '/#how' },
      },
      {
        id: 'how-does-expotofunnel-work',
        q: 'How does ExpoToFunnel work?',
        paragraphs: [
            'Three steps. Find: describe your ideal customer and get your top six trade shows ranked by buyer density,free in 90 seconds. Meet: our team identifies matching attendees and books confirmed meetings before the show opens. Talk: every meeting comes with a tailored brief.',
          'Step one is self serve and costs nothing. You fill in six fields about who you sell to, where your buyers are, your typical deal value, how differentiated you are, and how many clients you have served. You get a ranked shortlist with a fit grade and a written explanation for each show, plus a PDF report by email.',
          'Steps two and three are done for you. Once you engage us we move from event level to attendee level, identify the individual people at that show who match your buyer profile, run outreach six to eight weeksahead, and lock confirmed slots into your calendar. Each of those meetings arrives with a brief covering what that buyer cares about right now and how to open the conversation.',        ],
      
        related: { label: 'See how it works', href: '/#how' },
      },
      {
        id: 'who-is-expotofunnel-for',
        q: 'Who is ExpoToFunnel for?',
        paragraphs: [
          'B2B companies with deal values from $10,000 upward that sell into industries with an active trade show calendar. That includes sales leaders and founders attending without a booth, and field marketing teams responsible for booth performance at events they already exhibit at.',
          'The product works best for B2B companies with strong differentiation and local reference clients. If your average deal is lower, we will still work for you - but the ROI justification becomes harder.',
        ],
      },
      {
        id: 'is-expotofunnel-software-or-a-service',
        q: 'Is ExpoToFunnel software or a service?',
        paragraphs: [
          'At the first level, we are a web service that recommends the best trade shows where your ideal customer profile is likely to attend. The trade show ranking is easy: you fill in a form and get an instant scored shortlist with no human involved. The meeting booking, the outreach and the per-meeting briefs are delivered by our employees, not automated',
'We are explicit about this split because it changes what you should expect. The free ranking is immediate. Booked meetings take six to eight weeks of real outreach work by real people, backed by a company that has been doing this for a long time - which is why they are priced per confirmed meeting rather than per seat',
        ],
      },
      {
        id: 'what-is-the-difference-between-expotofunnel-and',
        q: 'What is the difference between ExpoToFunnel and LeadStrategus?',
        paragraphs: [
          'LeadStrategus is the company. ExpoToFunnel is its trade show product. LeadStrategus is a B2B demand generation and go to market consulting firm based in Bangalore, India, and ExpoToFunnel productises the part of that practice concerned with choosing events and filling calendars at them',
          'If you work with us on a paid package, the team delivering your outreach and meeting briefs is the LeadStrategus team, whose background includes enterprise go-to-market work at organisations such as AWS, SAP, Gartner and Oracle.',
        ],
      },
      {
        id: 'do-i-need-to-exhibit-at-a-trade-show-to-use-expotofunnel',
        q: 'Do I need to exhibit at a trade show to use ExpoToFunnel?',
        paragraphs: [
          'No. ExpoToFunnel works for companies attending without a booth as well as for exhibitors. Attending with a pre-booked calendar costs a fraction of exhibiting and often returns more, because the cost is a pass and travel rather than stand space and build.',
          'For attendees the goal is a full day-one calendar before you fly. For exhibitors the goal is booth slots filled with matched buyers rather than walk-up traffic. The underlying work is the same: find the people worth meeting and book them in advance.',
        ],
      },
            {
        id: 'book-meetings-for-few',
        q: 'Can you book meetings for a show I have already chosen, outside your top six??',
        paragraphs: [
          'Yes. The free ranking is the fastest way to find out which shows are worth attending, but if you are already committed to an event - including flagship shows like Dreamforce or Gartner Symposium - we can run the same outreach and meeting-booking engine against it. Tell us the event and we will scope a package against it directly',
        ],
      },
    ],
  },
  {
    id: 'the-free-ranking',
    heading: 'The free ranking',
    questions: [
      {
        id: 'is-the-free-tier-really-free',
        q: 'Is the free tier really free?',
        paragraphs: [
          'Yes. Discover shows your top six ranked events, ICP counts, fit grades, dates and locations, and a downloadable PDF report at no cost, with no time limit and no credit card required. There is no trial period that expires and no card to cancel.',
          'The free tier exists because the ranking is the part we can automate. We would rather you see the quality of the analysis before deciding whether to pay us to act on it.',
        ],
      
        related: { label: 'Try the free ranking', href: '/#icp-form' },
      },
      {
        id: 'what-do-i-get-with-the-free-ranking',
        q: 'What do I get with the free ranking?',
        paragraphs: [
          'Your top six B2B trade shows ranked by ICP density, each with a letter fit grade, an estimated count of matching buyers attending, the location and dates, a cost signal, and a plain English explanation of why that show made your list. Plus a branded PDF report by email.',
          'The written rationale matters more than the ranking itself. Any tool can produce an ordered list. The rationale tells you what the model saw in your buyer profile and in that event’s attendee composition, so you can judge whether the logic holds for your business.',
        ],
      },
      {
        id: 'what-information-do-i-need-to-provide',
        q: 'What information do I need to provide?',
        paragraphs: [
          'Six inputs. Who you sell to as a role plus industry, the regions where your buyers attend events, your typical deal value, how strong your differentiator is on a scale of one to ten, how many unique clients you have served, and a work email to send the report to.',
          'You can optionally add the names of some existing clients. That helps identify events where companies similar to your customers already buy, which usually sharpens the ranking.',
          'The more specific the buyer description, the better the output. “CTOs at mid market fintech companies” produces a materially better shortlist than “fintech”.',
        ],
      },
      {
        id: 'how-long-does-the-ranking-take',
        q: 'How long does the ranking take?',
        paragraphs: [
          'Ninety seconds from submitting the form. The ranked shortlist appears on screen immediately and the branded PDF report follows by email shortly afterwards.',
        ],
      },
      {
        id: 'why-only-six-shows',
        q: 'Why only six shows?',
        paragraphs: [
          'For technical categories where you are a founder-driven sales organisation, or you need deep subject matter experts to speak with prospects, six is a good number to execute. Nothing prevents you from doing more, but that needs to be part of your planned GTM with assigned specialists dedicated to trade shows as part of their day jobs. A list of forty shows is a research document, not a plan. If you want the full ranked list including shows seven through twenty-three, that is included in the paid packages.',
        ],
      },
      {
        id: 'will-someone-call-me-after-i-submit-the-form',
        q: 'Will someone call me after I submit the form?',
        paragraphs: [
          'No. There is no sales call attached to the free tier. Your work email is used to send your PDF report. If you want to talk to us about filling your calendar at one of the shows, you contact us.',
        ],
      },
      {
        id: 'do-i-need-a-credit-card-to-use-the-free-tier',
        q: 'Do I need a credit card to use the free tier?',
        paragraphs: [
          'No. Discover requires no payment details of any kind and has no time limit.',
        ],
      },
    ],
  },
  {
    id: 'how-shows-are-ranked',
    heading: 'How shows are ranked',
    questions: [
      {
        id: 'how-does-expotofunnel-rank-trade-shows',
        q: 'How does ExpoToFunnel rank trade shows?',
        paragraphs: [
          'By ICP density first, which is the share of an event’s attendees who match your ideal customer profile, then by absolute reachable buyer count, seniority mix, total landed cost and timing against your pipeline. Those five factors are weighted into a single letter fit grade per event.',
          'Two model passes are used. The first produces the ranking and the rationale. The second validates that rationale against the underlying event data before it is shown to you, which catches cases where the reasoning does not actually support the score.',
        ],
      },
      {
        id: 'what-is-icp-density',
        q: 'What is ICP density?',
        paragraphs: [
          'ICP density is the percentage of a trade show’s attendees who match your ideal customer profile by role, industry, company size and geography. In our ranking model it’s the strongest single predictor we weight for trade show return, and it doesn’t depend on how large or well known the event is.',
          'A show with 40,000 attendees and 2 percent density puts 800 potential buyers in the building. A show with 4,000 attendees and 30 percent density puts 1,200 there, with far less noise and usually at a lower cost.',
          'Density also affects how your outreach lands. At a high density event your meeting request reads as relevant, because the recipient is attending for reasons adjacent to what you sell.',
        ],
      },
      {
        id: 'what-is-a-fit-grade',
        q: 'What is a fit grade?',
        paragraphs: [
          'A fit grade is a letter grade assigned to each event, calculated across five weighted factors: ICP density, absolute reachable buyer count, seniority mix, total landed cost including travel, and timing relative to your pipeline. It condenses the full scoring model into one comparable figure.',
        ],
      },
      {
        id: 'why-does-a-smaller-show-sometimes-rank-higher-than-a-bigger',
        q: 'Why does a smaller show sometimes rank higher than a bigger one?',
        paragraphs: [
          'Because attendee count is a vanity metric. What determines your return is how many of the people in the room can buy from you, not how many people are in the room. A focused vertical event frequently puts more of your buyers in front of you than a large horizontal one.',
          'Cost compounds this. Large flagship events carry higher pass prices, higher stand rates and more expensive hotels in the host city during the show week. A smaller event with triple the density at a third of the landed cost is not a close call.',
        ],
      },
      {
        id: 'how-many-trade-shows-are-in-the-index',
        q: 'How many trade shows are in the index?',
        paragraphs: [
          '17,007 B2B trade shows across 129 countries. The index is refreshed continuously, with events re verified on a rolling schedule for dates, venue, organiser and attendance changes.',
        ],
      },
      {
        id: 'where-does-the-event-data-come-from',
        q: 'Where does the event data come from?',
        needsInput: 'The specific data sources you are comfortable disclosing publicly.',
        paragraphs: [
          'A curated event database combined with live event data sources and continuous research passes organised by region and industry. Events are re verified on a rolling schedule rather than refreshed once a year.',
        ],
      },
      {
        id: 'how-current-is-the-event-data',
        q: 'How current is the event data?',
        paragraphs: [
          'The index is refreshed on a continuous rolling basis. Results default to a twelve month window starting from next month, and you can filter by timeframe once you have your list.',
          'Event dates and venues do change after publication. Always confirm dates against the organiser’s own site before booking travel.',
        ],
      },
      {
        id: 'do-event-organisers-pay-to-rank-higher',
        q: 'Do event organisers pay to rank higher?',
        paragraphs: [
          'No. No event organiser pays us anything, and no ranking on this site can be bought. Your shortlist is scored against your buyer profile, not against our commercial interests.',
          'This is the reason we will sometimes tell you that the event you were already planning to attend is not worth the flight. A recommendation engine that recommends everything is a directory.',
        ],
      },
      {
        id: 'what-if-my-industry-or-region-is-not-covered',
        q: 'What if my industry or region is not covered?',
        paragraphs: [
          'The index covers 129 countries and most B2B verticals with an active event calendar, but coverage depth varies. If your shortlist comes back thin or the fit grades are all low, that is usually a genuine signal that trade shows are not the right channel for your buyer rather than a gap in our data.',
          'If you think the coverage is wrong for your market, tell us. We prioritise research passes by demand.',
        ],
      },
      {
        id: 'can-i-see-shows-ranked-beyond-the-top-six',
        q: 'Can I see shows ranked beyond the top six?',
        paragraphs: [
          'Yes, on paid packages. Starter Pack includes shows ranked seven through twenty three. Growth Pack adds a full event calendar plan across multiple shows rather than a single ranked list.',
        ],
      },
    ],
  },
  {
    id: 'meetings-and-outreach',
    heading: 'Meetings and outreach',
    questions: [
      {
        id: 'what-counts-as-a-qualified-meeting',
        q: 'What counts as a qualified meeting?',
        paragraphs: [
          'A confirmed meeting slot with a decision maker or influencer at a company that matches your target industries, personas and geography, secured through pre event outreach on your behalf. A badge scan is not a qualified meeting. A confirmed calendar slot with a named, matching individual is.',
          'We count only confirmed slots. Someone saying they will try to swing by the stand does not count and is not billed.',
        ],
      },
      {
        id: 'who-books-the-meetings',
        q: 'Who books the meetings?',
        paragraphs: [
          'Our team. We identify the attendees who match your ICP, write and run the outreach, handle the back and forth on scheduling, and put confirmed slots into your calendar. You do not run the sequences yourself.',
        ],
      },
      {
        id: 'how-far-in-advance-does-outreach-start',
        q: 'How far in advance does outreach start?',
        paragraphs: [
          'Six to eight weeks before the event. Earlier than that and attendees have not committed to their schedule. Later and the good slots are gone. The most valuable slots, day one morning, are typically claimed four to five weeks out.',
          'This is the main practical constraint on engaging us. If an event is three weeks away, we can still book meetings, but the achievable volume drops sharply and we will tell you that before you commit.',
        ],
      },
      {
        id: 'how-do-you-find-out-who-is-attending-an-event',
        q: 'How do you find out who is attending an event?',
        paragraphs: [
          'Through a combination of organiser registration and exhibitor data where it is published, event platforms and apps, public attendance signals from the companies and individuals themselves, and our own research on which accounts are active around a given show.',
          'Attendee visibility varies enormously by event. Some organisers publish detailed exhibitor and delegate information. Others publish almost nothing. Where visibility is poor we will tell you before you buy, because it directly limits how many meetings we can commit to.',
        ],
      },
      {
        id: 'what-do-you-say-in-the-outreach',
        q: 'What do you say in the outreach?',
        paragraphs: [
          'For VIP and high-priority accounts, we warm the relationship where possible - engaging with their content before ever reaching out - so the meeting request lands as familiar rather than cold. This is not run on every account; it is reserved for the accounts that matter most.',
          'For the broader list, outreach references why that specific event and why that specific person, based on what their company is dealing with right now, and proposes concrete time slots. It is not a generic meeting request with the event name pasted in.',
          'In our experience, acceptance rates on event outreach run well above cold outbound, because the event supplies a legitimate, time-bound reason to meet. That advantage disappears the moment the message reads as a template.',
        ],
      },
      {
        id: 'do-you-contact-prospects-using-my-name-or-yours',
        q: 'Do you contact prospects using my name or yours?',
        needsInput: 'Your exact sending setup - e.g. whether you send from the client’s domain or a variant, and whether the client reviews copy before it goes out.',
        paragraphs: [
          'Outreach goes out on your behalf, representing your company. The buyer’s first interaction is with your brand, not with an agency they have never heard of.',
        ],
      },
      {
        id: 'what-is-a-meeting-brief-and-what-is-in-it',
        q: 'What is a meeting brief and what is in it?',
        paragraphs: [
          'A meeting brief is a document produced for each booked meeting. It covers what that buyer is dealing with right now, drawn from their company news, hiring activity and public posts, why your offer fits that situation, and the opener most likely to earn a second conversation.',
          'The point is that no two buyers get the same pitch. A VP of Procurement who just opened a plant in Munich and a CTO who has been posting about integration problems need different first sentences from you, and the brief tells you what those are.',
        ],
      },
      {
        id: 'do-you-support-us-during-the-event-itself-or-just-before-it',
        q: 'Do you support us during the event itself, or just before it?',
        paragraphs: [
          'Both. Every confirmed meeting comes with a brief, and on packages that include on-ground support, we provide real-time updates if a prospect’s situation changes, help you pivot messaging on the spot, and coordinate logistics on-site so slots don’t collide.',
          'The work doesn’t stop when the outreach is booked. It continues through the show floor, with live account intelligence for every confirmed meeting and support to keep your team’s day running on schedule.',
        ],
      },
      {
        id: 'how-many-meetings-can-i-realistically-run-in-one-show-day',
        q: 'How many meetings can I realistically run in one show day?',
        paragraphs: [
          'The ideal number is between five and eight per person per day. We have had some clients push beyond ten, but they have been doing this for a long time - or they would have launched something for which there is a strong pull in the market. Beyond that you are rushing conversations and losing the buffer you need for overruns, travel between halls, and the unplanned conversations that trade shows are actually good for.',
          'This is why package sizes are what they are. Ten meetings is roughly a focused two-day show for one person. Twenty is a two-day show for a small team, or a multi-show programme.',
        ],
      },
      {
        id: 'what-happens-if-someone-does-not-show-up',
        q: 'What happens if someone does not show up?',
        needsInput: 'Your actual no-show policy - e.g. whether a no-show is replaced, credited, or counted against the package.',
        paragraphs: [
          'No show rates at trade shows are never zero, which is why we reconfirm every booked meeting shortly before the event.',
        ],
      },
      {
        id: 'do-you-handle-follow-up-after-the-event',
        q: 'Do you handle follow up after the event?',
        paragraphs: [
          'Yes. Post event follow up is included in Starter Pack and above. The meetings are only worth what happens after them, and follow up that goes out cold four days late is where most trade show pipeline dies.',
        ],
      },
    ],
  },
  {
    id: 'pricing-and-packages',
    heading: 'Pricing and packages',
    questions: [
      {
        id: 'how-much-does-expotofunnel-cost',
        q: 'How much does ExpoToFunnel cost?',
        paragraphs: [
          'The trade show ranking is free forever. Starter Pack starts at $4,000 for 10 confirmed qualified meetings for SMB decision makers. Growth Pack starts at $6,000 for 20 confirmed qualified meetings plus a named ICP account list. Full Takeover is scoped per flagship event for 50 or more meetings.',
          'Pricing is per confirmed qualified meeting. All prices are in USD, plus local taxes as applicable.',
        ],
      
        related: { label: 'See full pricing', href: '/pricing' },
      },
      {
        id: 'what-is-the-difference-between-starter-pack-and-growth-pack',
        q: 'What is the difference between Starter Pack and Growth Pack?',
        paragraphs: [
          'Starter Pack delivers 10 confirmed meetings and includes shows ranked seven through twenty three, pre show ICP outreach and post event follow up. Growth Pack delivers 20 confirmed meetings and adds a full event calendar plan, multi show strategy and a named ICP account list.',
          'Starter suits one event. Growth suits a planned run of events across a quarter or a year, where the value is in the calendar strategy as much as the individual meetings.',
        ],
      
        related: { label: 'Compare packages', href: '/pricing' },
      },
      {
        id: 'what-is-full-takeover',
        q: 'What is Full Takeover?',
        paragraphs: [
          'Full Takeover is a custom scoped programme for a flagship event, targeting 50 or more meetings. It includes a dedicated researcher, full outreach copy and sequence development, on site coordination during the event, and an outcomes guarantee defined in your written agreement.',
          'It is designed for the one or two events a year that genuinely matter to a business, where the budget is already large and the cost of the event underperforming is high.',
        ],
      },
      {
        id: 'how-does-the-cost-per-meeting-compare-to-a-booth',
        q: 'How does the cost per meeting compare to a booth?',
        paragraphs: [
          'Starter Pack works out at roughly $400 per confirmed qualified meeting and Growth Pack at roughly $300. A mid size booth costing $40,000 that produces eight qualified conversations works out at $5,000 per meeting.',
          'That comparison is the core argument for pre booking, and it is worth running with your own numbers rather than ours. Take your last event’s total cost, including stand, build, travel, hotels and staff days, and divide it by the number of conversations that turned into a real opportunity.',
        ],
      },
      {
        id: 'can-i-upgrade-after-starting-on-discover',
        q: 'Can I upgrade after starting on Discover?',
        paragraphs: [
          'Yes. You can move to Starter Pack, Growth Pack or a custom Full Takeover arrangement at any time by contacting us. We will scope the package to the events you actually plan to attend rather than to a fixed tier.',
        ],
      },
      {
        id: 'do-you-charge-per-event-or-per-year',
        q: 'Do you charge per event or per year?',
        needsInput: 'Whether meetings in a package must be used at one event or can be spread across several, and whether unused meetings expire.',
        paragraphs: [
          'Packages are scoped against the events you plan to attend. Starter is typically a single event. Growth commonly spans a multi show calendar. Full Takeover is priced per flagship event.',
        ],
      },
      {
        id: 'do-you-work-with-companies-outside-the-uk-india-and-the',
        q: 'Do you work with companies outside the UK, India and the United States?',
        paragraphs: [
          'Yes. The index covers 129 countries and we run programmes into European, Gulf and Asia Pacific events. Those three are simply where most of our current clients are based.',
        ],
      },
    ],
  },
  {
    id: 'results-and-guarantees',
    heading: 'Results and guarantees',
    questions: [
      {
        id: 'do-you-guarantee-outcomes',
        q: 'Do you guarantee outcomes?',
        paragraphs: [
          'Full Takeover packages include an outcomes guarantee, defined in your written agreement. Starter and Growth packages are delivered on a best effort basis against the stated meeting target. We state that plainly rather than implying a guarantee we have not given.',
          'What we can commit to on every package is the process: the research, the outreach volume, the reconfirmation and the briefs. What no honest provider can commit to on a smaller package is the behaviour of the buyers on the other end.',
        ],
      },
      {
        id: 'have-you-actually-delivered-this-before',
        q: 'Have you actually delivered this before?',
        paragraphs: [
          'Yes. At BSMA Summit 2024 (Brussels, 3,500 attendees), we reached 280 companies, connected with 75, generated 18 meeting requests, and surfaced 12 Fortune 50 opportunities for one client - 5x the qualified meeting rate of standard event attendance.',
          'The estimate formula below tells you what to expect for your event; this is what it looked like for one real one.',
        ],
      },
      {
        id: 'how-is-the-meeting-estimate-calculated',
        q: 'How is the meeting estimate calculated?',
        paragraphs: [
          'From event attendee data, your stated deal size and client history, and industry benchmark conversion rates. It is an estimate, not a guarantee, and it is shown alongside the assumptions behind it so you can judge it for yourself.',
          'If you disagree with an assumption, the estimate is wrong for you, and we would rather you see that than take the number on trust.',
        ],
      },
      {
        id: 'what-results-should-i-expect',
        q: 'What results should I expect?',
        needsInput: 'Your own delivered results once citable - e.g. average meetings booked per engagement, or average cost per qualified meeting across clients.',
        paragraphs: [
          'That depends on your deal size, win rate and the density of the event. The honest answer is to run the arithmetic before you commit: total event cost divided by the revenue a single qualified meeting is worth to you gives you the number of meetings the event needs to produce to break even.',
        ],
      },
      {
        id: 'how-do-i-measure-trade-show-roi',
        q: 'How do I measure trade show ROI?',
        paragraphs: [
          'Trade show ROI is your net return on the event divided by its total cost: (revenue generated minus total event cost) divided by total event cost. Revenue generated equals qualified meetings multiplied by your meeting-to-opportunity conversion rate, your opportunity win rate, and your average deal value. Total event cost must include staff time, travel and accommodation, not just booth space, or the number is fiction.',
          'Break-even meetings equals total event cost divided by (meeting-to-opportunity conversion rate multiplied by win rate multiplied by average deal value). A company with a $50,000 average contract value, a 25 percent win rate, a 30 percent meeting-to-opportunity conversion rate, and $36,000 in total event cost needs roughly ten qualified meetings to break even. Change any one of those assumptions and the ten changes with it - the formula is only as good as the inputs you put into it.',
          'Measure at twelve months, not at quarter end. If your sales cycle is six to nine months, a quarter end review will tell you the event failed when the pipeline it created has not closed yet.',
        ],
      
        related: { label: 'See package pricing', href: '/pricing' },
      },
      {
        id: 'what-if-the-ranking-says-none-of-my-shows-are-worth',
        q: 'What if the ranking says none of my shows are worth attending?',
        paragraphs: [
          'Then that is the finding, and it has saved you the cost of the event. Low fit grades across your whole shortlist usually mean one of three things: your buyer profile is too broad, your deal size is too small for event economics to work, or your buyers genuinely do not attend trade shows.',
          'We would rather tell you that for free than take money to fill a calendar at an event that was never going to pay back.',
        ],
      },
    ],
  },
  {
    id: 'data-and-privacy',
    heading: 'Data and privacy',
    questions: [
      {
        id: 'what-do-you-do-with-my-work-email',
        q: 'What do you do with my work email?',
        paragraphs: [
          'Your email is used to send your PDF event report. We do not sell your data and there is no sales call attached to the free tier.',
          'We keep submitted profiles and search history only as long as reasonably needed, and in any case no longer than 24 months after your last activity, unless you ask us to delete it sooner. Full details, including our other data retention rules and every third party processor we use, are in our Privacy Policy.',
        ],
      
        related: { label: 'Read our Privacy Policy', href: '/privacy' },
      },
      {
        id: 'is-my-icp-information-shared-with-anyone',
        q: 'Is my ICP information shared with anyone?',
        paragraphs: [
          'No, we do not sell it. The buyer profile you submit is used to generate your ranking and your report, and is shared only with the specific service providers needed to run the Service (our AI, embedding, and enrichment providers) or with our internal team if you request a paid package. See our Privacy Policy for the complete list.',
        ],
      
        related: { label: 'Read our Privacy Policy', href: '/privacy' },
      },
      {
        id: 'is-it-legal-to-contact-trade-show-attendees-before-the-event',
        q: 'Is it legal to contact trade show attendees before the event?',
        paragraphs: [
          'B2B outreach to business contacts is lawful in most jurisdictions where ExpoToFunnel operates, subject to the rules that apply in the recipient’s country, including GDPR in the UK and EU, CAN SPAM in the United States, and the DPDP Act in India. The applicable rules differ by market and by channel.',
          'We run outreach in line with the requirements of the market being contacted. If you have specific compliance requirements from your own legal team, tell us at scoping and we will work to them.',
          'This is general information about how we operate and not legal advice. For a binding answer on your own obligations, ask your legal counsel.',
        ],
      },
    ],
  },
  {
    id: 'getting-started',
    heading: 'Getting started',
    questions: [
      {
        id: 'how-do-i-get-started',
        q: 'How do I get started?',
        paragraphs: [
          'Run the free ranking first. It takes 90 seconds, needs no credit card and gives you your top six shows with fit grades and a PDF report. If you want us to fill the calendar at one of them, contact us from there.',
        ],
      
        related: { label: 'Try the free ranking', href: '/#icp-form' },
      },
      {
        id: 'how-quickly-can-you-start-work-on-an-event',
        q: 'How quickly can you start work on an event?',
        paragraphs: [
          'As soon as the package is scoped. The binding constraint is the event date, not our availability: outreach needs six to eight weeks before the show to hit full meeting volume.',
          'If your event is closer than that, tell us the date and we will give you an honest view of what is achievable rather than selling you a package that cannot deliver.',
        ],
      },
      {
        id: 'what-do-you-need-from-me-to-run-a-package',
        q: 'What do you need from me to run a package?',
        paragraphs: [
          'Your ideal customer profile, the events you are attending or considering, your typical deal value, and enough about your offer for us to write outreach and briefs that sound like you. Then a calendar to book into and the names of who is travelling.',
          'The single input that most affects results is the specificity of your buyer profile. “Heads of Supply Chain at pharmaceutical manufacturers in the DACH region” gives us something to work with. “Enterprise companies” does not.',
        ],
      },
    ],
  },
]

// Flat list of every question, in page order - used to generate the
// JSON-LD FAQPage schema and for any "N questions" counts.
export const FAQ_FLAT = FAQ_CATEGORIES.flatMap(cat => cat.questions)
