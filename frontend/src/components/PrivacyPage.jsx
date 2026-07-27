/*
  PrivacyPage.jsx - Privacy Policy for the Global Event Discovery Agent
  (LeadStrategus). Content reflects what the product actually collects
  and does, not generic boilerplate - see the section list below.
*/
import LegalPage from './LegalPage'

const SECTIONS = [
  {
    id: 'overview',
    heading: 'Overview',
    paragraphs: [
      'This Privacy Policy explains how LeadStrategus ("we", "us", "our") collects, uses, stores, and shares information when you use the Global Event Discovery Agent (the "Service"), an AI powered tool that matches your ideal customer profile against a database of trade shows, conferences, and industry events.',
      'LeadStrategus is the data controller for the personal information described in this policy. You can reach us at the address in the “Questions about this policy?” section below:',
      'By submitting the ICP (Ideal Customer Profile) form or otherwise using the Service, you agree to the collection and use of information as described in this policy.',
    ],
  },
  {
    id: 'information-we-collect',
    heading: 'Information we collect',
    paragraphs: [
      'We collect information in three ways: what you type into the form, what our systems observe automatically while you use the Service, and files you choose to upload.',
    ],
    list: [
      'Form inputs: company name, work email address, a free text description of who you sell to, target industries, target personas or job titles, target geographies, preferred event types, typical deal size range, date range for your search, a 1 to 10 self rated competitive differentiation score, your client count range, and optionally the names of clients you have served.',
      'Uploaded files: if you choose to upload a pitch deck (PDF), we extract text from it to better understand your business. The file itself is processed by us and our AI and embedding providers to build this context. It is not published publicly or shared with anyone outside the providers listed below.',
      'Usage and session data: a session identifier, the page you arrived from (referrer), pages visited, time spent on the Service, and your IP address, collected automatically to understand how the Service is used and to keep it reliable.',
      'Search results and outcomes: the events shown to you, which ones were ranked as strong matches, and whether you requested an emailed report, so we can measure and improve match quality over time.',
    ],
  },
  {
    id: 'how-we-use-information',
    heading: 'How we use your information',
    paragraphs: [
      'We use the information you provide to power the core function of the Service: matching your ideal customer profile against our event database using a combination of rule based scoring and AI semantic matching, and ranking the results.',
    ],
    list: [
      'To generate your personalized list of ranked events and the associated fit analysis.',
      'To generate and email you a PDF report of your results, if you request one.',
      'To improve the accuracy of our matching and ranking systems over time.',
      'To operate, secure, and troubleshoot the Service, including detecting abuse or unusual activity.',
      'To follow up with you about our paid meeting setting packages (Starter Pack, Growth Pack, Full Takeover), only if you have expressed interest or requested contact.',
      'To build aggregated, non identifying analytics and reporting on how the Service is used, so we can plan future improvements.',
    ],
  },
    {
    id: 'outreach-on-your-behalf-and-third-party-contacts',
    heading: 'Outreach on your behalf and third-party contacts',
    paragraphs: [
      'For paid packages, we conduct outreach to potential meeting contacts at target companies on your behalf. To do this we process business contact information (such as name, job title, company, and business email) for individuals at companies matching your ideal customer profile. This information is obtained from publicly available sources and licensed business-data providers',
      'We process this data on the basis of our and your legitimate interests in business-to-business relationship-building, balanced against the rights of the individuals contacted. Where required by applicable law, outreach is conducted only through permitted channels and includes clear identification of the sender and a means to opt out. Individuals contacted may object to this processing or request deletion at any time by contacting kingshuk@leadstrategus.com.',
      'You remain responsible for complying with your own obligations under applicable anti-spam and data-protection law when you communicate with any contact introduced to you through the Service.',
    ],
  },
  {
    id: 'third-party-processors',
    heading: 'Third party service providers',
    paragraphs: [
      'We rely on a small number of specialist third party providers to deliver the Service. Each processes only the data needed to perform its function, and none are permitted to use your data for their own independent purposes.',
    ],
    list: [
      'AI language model providers, used to parse your free text description, rank and validate event relevance, and generate written rationale for each recommended event.',
      'An embedding provider, used to convert event and profile text into vector representations so that semantic (meaning based) matching can take place alongside keyword matching.',
      'A web search and enrichment provider, used to fill in missing event details such as attendee counts, pricing, and registration links from publicly available sources.',
      'A transactional email provider, used solely to deliver the PDF report to the email address you provide.',
      'A hosted database provider, used to store your submitted profile, search results, and analytics records securely.',
    ],
  },
  {
    id: 'sharing',
    heading: 'How we share information',
    paragraphs: [
      'We do not sell your personal information. We share information only as described in this policy: with the third party processors listed above, to the extent needed to run the Service; with our internal team if you request a paid package or otherwise ask to be contacted; or if required to do so by law, regulation, or a valid legal process.',
    ],
  },
  {
    id: 'retention',
    heading: 'Data retention',
    paragraphs: [
      'We retain your submitted profile and search history for as long as reasonably needed to provide the Service, respond to your requests, and maintain accurate analytics, and in any case for no longer than 24 months after your last activity unless you ask us to delete it sooner. If you ask us to delete your data, we will do so within a reasonable time, except where we are required to retain certain records for legal, security, or accounting reasons.',
    ],
  },
  {
    id: 'your-rights',
    heading: 'Your rights and choices',
    paragraphs: [
      'Depending on where you are located, you may have rights to access, correct, export, or delete the personal information we hold about you, and to object to or restrict certain uses of it. To exercise any of these rights, contact us using the details at the bottom of this page and we will respond as required by applicable law.',
    ],
  },
  {
    id: 'cookies',
    heading: 'Cookies and similar technologies',
    paragraphs: [
      'The Service uses a session identifier stored in your browser to link your activity to a single session for analytics purposes, such as measuring how long a session lasted and which pages were viewed. This identifier does not track you across other, unrelated websites.',
    ],
  },
  {
    id: 'security',
    heading: 'Security',
    paragraphs: [
      'We use industry standard safeguards, including encrypted connections (HTTPS) and access controls on our systems, to protect the information you provide. No method of transmission or storage is completely secure, and we cannot guarantee absolute security.',
    ],
  },
  {
    id: 'international-transfers',
    heading: 'International data transfers',
    paragraphs: [
      'Because we rely on third party providers that operate infrastructure in multiple countries, your information may be processed outside the country in which you are located. Where we transfer personal data outside the UK or EEA, we rely on an appropriate safeguard recognised under applicable law, such as an adequacy decision or the applicable Standard Contractual Clauses, and we can provide details of the safeguard used on request.',
    ],
  },
  {
    id: 'children',
    heading: "Children's privacy",
    paragraphs: [
      'The Service is intended for business use by adults and is not directed at children. We do not knowingly collect personal information from anyone under the age of 18. If you believe a child has provided us with personal information, please contact us and we will remove it.',
    ],
  },
  {
    id: 'changes',
    heading: 'Changes to this policy',
    paragraphs: [
      'We may update this Privacy Policy from time to time to reflect changes in the Service or applicable law. When we do, we will revise the "Last updated" date at the top of this page. Continued use of the Service after an update means you accept the revised policy.',
    ],
  },
  {
    id: 'company-details',
    heading: 'Company details',
    paragraphs: [
      'The Service is provided by LeadStrategus Private Limited, and this policy is governed by the laws of India.',
    ],
    list: [
      'Registered office: C/o WeWork Zenia, Hiranandani Circle, Thane West, 400607, India',
      'Bengaluru office: Brigade Tech Park, near ITPL Main Road, Pattandur Agrahara, Whitefield, Bengaluru, Karnataka 560066, India',
    ],
  },
]

export default function PrivacyPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Privacy Policy"
      updated="July 27, 2026"
      sections={SECTIONS}
    />
  )
}
