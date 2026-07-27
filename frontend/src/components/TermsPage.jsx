/*
  TermsPage.jsx - Terms of Service for the Global Event Discovery Agent
  (LeadStrategus).
*/
import LegalPage from './LegalPage'

const SECTIONS = [
  {
    id: 'acceptance',
    heading: 'Acceptance of terms',
    paragraphs: [
      'These Terms of Service ("Terms") govern your access to and use of the Global Event Discovery Agent (the "Service"), provided by LeadStrategus ("we", "us", "our"). By submitting the ICP form, viewing your results, or otherwise using the Service, you agree to be bound by these Terms. If you do not agree, do not use the Service.',
    ],
  },
  {
    id: 'the-service',
    heading: 'Description of the Service',
    paragraphs: [
      'The Service is an AI assisted research tool that matches a description of your target customer against a database of trade shows, conferences, and industry events, and returns a ranked list of events with an estimated fit score, rationale, and meeting potential estimate.',
      'The free tier of the Service shows a limited number of top ranked events. Paid packages (Starter Pack, Growth Pack, Full Takeover) offer expanded event coverage and hands on meeting setting services, described further on our pricing page and confirmed separately in writing before any payment is due.',
    ],
  },
  {
    id: 'eligibility',
    heading: 'Eligibility and accounts',
    paragraphs: [
      'The Service is intended for business use by individuals who are at least 18 years old and are authorized to provide information on behalf of the company they represent. You are responsible for the accuracy of the information you submit, including your work email address.',
    ],
  },
  {
    id: 'acceptable-use',
    heading: 'Acceptable use',
    paragraphs: [
      'When using the Service, you agree not to:',
    ],
    list: [
      'Scrape, copy, or systematically extract event data from the Service for use in a competing product or database.',
      'Attempt to reverse engineer, decompile, or interfere with the scoring, ranking, or matching systems.',
      'Submit false information, impersonate another company or person, or use the Service for any unlawful purpose.',
      'Use event contact or attendee information obtained through the Service to send unsolicited bulk communications in violation of applicable anti spam law.',
      'Overload, disrupt, or attempt unauthorized access to the Service or the systems it depends on.',
    ],
  },
  {
    id: 'data-accuracy',
    heading: 'Event data accuracy',
    paragraphs: [
      'Event details such as dates, locations, attendee estimates, and pricing are aggregated from public listings, event organizer websites, and third party enrichment sources, and may change without notice. We work to keep this data current but do not guarantee it is complete, accurate, or up to date at the moment you view it.',
      'You are responsible for verifying event details directly with the organizer before making travel, budget, or registration decisions.',
    ],
  },
  {
    id: 'intellectual-property',
    heading: 'Intellectual property',
    paragraphs: [
      'The Service, including its matching methodology, scoring formulas, design, and underlying software, is owned by LeadStrategus and protected by applicable intellectual property law. Event names, logos, and third party content referenced in the Service belong to their respective owners.',
      'We grant you a limited, non exclusive, non transferable right to use the Service for your own internal business purposes. All other rights are reserved.',
    ],
  },
  {
    id: 'paid-packages',
    heading: 'Paid packages',
    paragraphs: [
      'Prices shown for the Starter Pack, Growth Pack, and Full Takeover packages are indicative starting prices, quoted in USD, and are not a binding offer. All fees are exclusive of local taxes, which apply as required by law based on your billing location. A binding quote, scope of work, and payment terms are provided separately once you contact us and confirm your requirements.',
      'Refund, cancellation, and delivery terms for paid packages are governed by the separate written agreement you enter into with us for that package, not by these Terms.',
    ],
  },
  {
    id: 'disclaimer',
    heading: 'Disclaimer of warranties',
    paragraphs: [
      'The Service is provided "as is" and "as available" without warranties of any kind, express or implied, including but not limited to warranties of merchantability, fitness for a particular purpose, or non infringement. We do not warrant that the Service will be uninterrupted, error free, or that any event recommendation will result in a specific business outcome.',
    ],
  },
  {
    id: 'limitation-of-liability',
    heading: 'Limitation of liability',
    paragraphs: [
      'To the maximum extent permitted by law, LeadStrategus and its officers, employees, and partners will not be liable for any indirect, incidental, special, consequential, or punitive damages, or for any loss of profits, revenue, or business opportunity, arising from your use of or inability to use the Service, even if we have been advised of the possibility of such damages.',
      'Our total liability for any claim arising from the Service will not exceed the amount, if any, you paid us in the twelve months preceding the claim.',
    ],
  },
  {
    id: 'termination',
    heading: 'Termination',
    paragraphs: [
      'We may suspend or terminate your access to the Service at any time if we reasonably believe you have violated these Terms. You may stop using the Service at any time. Sections of these Terms that by their nature should survive termination, including intellectual property, disclaimers, and limitation of liability, will continue to apply.',
    ],
  },
  {
    id: 'changes',
    heading: 'Changes to these Terms',
    paragraphs: [
      'We may update these Terms from time to time. When we do, we will revise the "Last updated" date at the top of this page. Continued use of the Service after an update means you accept the revised Terms.',
    ],
  },
  {
    id: 'governing-law',
    heading: 'Governing law',
    paragraphs: [
      'These Terms are governed by the laws of India, without regard to conflict of law principles, unless a separate written agreement between you and LeadStrategus states otherwise. Any dispute arising from these Terms or the Service is subject to the exclusive jurisdiction of the courts having competent authority over LeadStrategus\'s registered office.',
    ],
  },
  {
    id: 'company-details',
    heading: 'Company details',
    paragraphs: [
      'The Service is provided by LeadStrategus Private Limited.',
    ],
    list: [
      'Registered office: C/o WeWork Zenia, Hiranandani Circle, Thane West, 400607, India',
      'Bengaluru office: Brigade Tech Park, near ITPL Main Road, Pattandur Agrahara, Whitefield, Bengaluru, Karnataka 560066, India',
    ],
  },
]

export default function TermsPage() {
  return (
    <LegalPage
      eyebrow="Legal"
      title="Terms of Service"
      updated="July 25, 2026"
      sections={SECTIONS}
    />
  )
}
