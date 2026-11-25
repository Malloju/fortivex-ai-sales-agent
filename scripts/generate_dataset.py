"""
scripts/generate_dataset.py - Generate and validate all required data files
Creates data/properties.csv, data/company_knowledge.txt, and data/sample_customers.csv,
initializes SQLite, and loads synthetic sample customers idempotently.
Safe to run multiple times - will not create duplicate or inconsistent records.
"""
import sys
import csv
import logging
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from backend import database as db
from backend.models import CustomerProfile
from backend import lead_qualification as lq

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ============================================================
# FICTIONAL DATASET DEFINITIONS (DreamHome Realty)
# ============================================================

PROPERTIES_DATA = [
    {
        "property_id": "P001",
        "property_name": "Sunrise Apartments - 2BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 4500000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 950,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Power Backup, Parking, Security, Gym",
        "possession_status": "Ready to Move",
        "description": "Spacious 2BHK apartment on 3rd floor with sunrise views, modular kitchen, well-ventilated rooms, and direct connectivity to NH-44.",
        "contact_information": "+91-98765-00001",
    },
    {
        "property_id": "P002",
        "property_name": "Sunrise Apartments - 3BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 6500000,
        "bedrooms": 3,
        "bathrooms": 2,
        "area_sqft": 1350,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Power Backup, Parking, Security, Gym, Clubhouse",
        "possession_status": "Ready to Move",
        "description": "Premium 3BHK apartment in Sunrise Apartments complex featuring modular kitchen, master en-suite, large living room, and 24/7 gated security.",
        "contact_information": "+91-98765-00001",
    },
    {
        "property_id": "P003",
        "property_name": "Green Valley Homes - 2BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 3800000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 870,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security, Water Tank, Garden Area",
        "possession_status": "Under Construction (Expected June 2027)",
        "description": "Affordable 2BHK in Green Valley Homes residential project with planned green park and good cross ventilation.",
        "contact_information": "+91-98765-00002",
    },
    {
        "property_id": "P004",
        "property_name": "Green Valley Homes - 3BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 5200000,
        "bedrooms": 3,
        "bathrooms": 2,
        "area_sqft": 1200,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security, Water Tank, Garden Area, Playground",
        "possession_status": "Under Construction (Expected June 2027)",
        "description": "Corner 3BHK unit in Green Valley Homes offering dual-aspect daylight, family balcony, and children's play area.",
        "contact_information": "+91-98765-00002",
    },
    {
        "property_id": "P005",
        "property_name": "Royal Enclave - 4BHK Independent House",
        "property_type": "Independent House",
        "location": "Phagwara",
        "price_inr": 9500000,
        "bedrooms": 4,
        "bathrooms": 3,
        "area_sqft": 2200,
        "furnishing": "Fully Furnished",
        "amenities": "Private Garden, Garage, Modular Kitchen, Inverter, Solar Water Heater",
        "possession_status": "Ready to Move",
        "description": "4BHK independent house with private lawn and two-car garage in peaceful Royal Enclave colony near Lovely Professional University.",
        "contact_information": "+91-98765-00003",
    },
    {
        "property_id": "P006",
        "property_name": "Lotus Heights - 1BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 2200000,
        "bedrooms": 1,
        "bathrooms": 1,
        "area_sqft": 550,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Security, Parking",
        "possession_status": "Ready to Move",
        "description": "Compact 1BHK apartment ideal for working professionals or small families, close to Phagwara Bus Stand and NH-44.",
        "contact_information": "+91-98765-00004",
    },
    {
        "property_id": "P007",
        "property_name": "Shivalik Residency - 3BHK",
        "property_type": "Apartment",
        "location": "Jalandhar",
        "price_inr": 7500000,
        "bedrooms": 3,
        "bathrooms": 2,
        "area_sqft": 1450,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Gym, Swimming Pool, Clubhouse, 24/7 Security, Power Backup, Parking",
        "possession_status": "Ready to Move",
        "description": "High-rise 3BHK apartment in Shivalik Residency with city views, chimney-equipped modular kitchen, and easy access to Jalandhar City Railway Station.",
        "contact_information": "+91-98765-00005",
    },
    {
        "property_id": "P008",
        "property_name": "Civil Lines Apartment - 2BHK",
        "property_type": "Apartment",
        "location": "Jalandhar",
        "price_inr": 5800000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 1050,
        "furnishing": "Fully Furnished",
        "amenities": "Lift, Power Backup, Security, Parking, WiFi Ready",
        "possession_status": "Ready to Move",
        "description": "Fully furnished 2BHK apartment in prestigious Civil Lines with modern appliances included, near Model Town market and schools.",
        "contact_information": "+91-98765-00006",
    },
    {
        "property_id": "P009",
        "property_name": "Punjabi Bagh Homes - 2BHK",
        "property_type": "Apartment",
        "location": "Jalandhar",
        "price_inr": 4200000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 920,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security, Rooftop Garden",
        "possession_status": "Ready to Move",
        "description": "Corner 2BHK flat in Punjabi Bagh featuring extra ventilation, rooftop garden access, and strong rental demand.",
        "contact_information": "+91-98765-00007",
    },
    {
        "property_id": "P010",
        "property_name": "Model Town Luxury Villa - 4BHK",
        "property_type": "Villa",
        "location": "Jalandhar",
        "price_inr": 18000000,
        "bedrooms": 4,
        "bathrooms": 4,
        "area_sqft": 3500,
        "furnishing": "Fully Furnished",
        "amenities": "Private Pool, Landscaped Garden, Double Garage, Home Theatre, Modular Kitchen, Smart Home",
        "possession_status": "Ready to Move",
        "description": "Ultra-luxury 4BHK villa in Model Town featuring smart home automation, private pool, landscaped garden, and imported marble flooring.",
        "contact_information": "+91-98765-00008",
    },
    {
        "property_id": "P011",
        "property_name": "Garden City Apartments - 3BHK",
        "property_type": "Apartment",
        "location": "Jalandhar",
        "price_inr": 8900000,
        "bedrooms": 3,
        "bathrooms": 3,
        "area_sqft": 1600,
        "furnishing": "Semi-Furnished",
        "amenities": "Gym, Swimming Pool, Jogging Track, Kids Zone, Clubhouse, Parking, Security",
        "possession_status": "Ready to Move",
        "description": "Park-facing 3BHK apartment with utility room inside a resort-style gated community near DAV University.",
        "contact_information": "+91-98765-00009",
    },
    {
        "property_id": "P012",
        "property_name": "Urban Nest - 2BHK",
        "property_type": "Apartment",
        "location": "Ludhiana",
        "price_inr": 5500000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 1000,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Gym, Power Backup, Parking, 24/7 Security",
        "possession_status": "Ready to Move",
        "description": "Contemporary 2BHK apartment in central Ludhiana near Westend Mall with an open-concept kitchen and fitness center.",
        "contact_information": "+91-98765-00010",
    },
    {
        "property_id": "P013",
        "property_name": "Sarabha Nagar Premium - 3BHK",
        "property_type": "Apartment",
        "location": "Ludhiana",
        "price_inr": 9800000,
        "bedrooms": 3,
        "bathrooms": 3,
        "area_sqft": 1750,
        "furnishing": "Fully Furnished",
        "amenities": "Gym, Swimming Pool, Clubhouse, Concierge, Valet Parking, Power Backup",
        "possession_status": "Ready to Move",
        "description": "Fully furnished 3BHK high-rise residence on the 15th floor in Sarabha Nagar with panoramic city views and smart locks.",
        "contact_information": "+91-98765-00011",
    },
    {
        "property_id": "P014",
        "property_name": "BRS Nagar Signature Villa - 3BHK",
        "property_type": "Villa",
        "location": "Ludhiana",
        "price_inr": 14500000,
        "bedrooms": 3,
        "bathrooms": 3,
        "area_sqft": 2800,
        "furnishing": "Semi-Furnished",
        "amenities": "Private Garden, Garage, Solar Power, RO Water System",
        "possession_status": "Ready to Move",
        "description": "Elegant 3BHK villa in quiet BRS Nagar residential lane with ground-floor master suite, private lawn, and solar power.",
        "contact_information": "+91-98765-00012",
    },
    {
        "property_id": "P015",
        "property_name": "Dugri Phase 2 - 2BHK",
        "property_type": "Apartment",
        "location": "Ludhiana",
        "price_inr": 4700000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 900,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security, Lift, Water Tank",
        "possession_status": "Ready to Move",
        "description": "Well-priced 2BHK apartment in Dugri Phase 2 near PAU with active resident welfare association and lift access.",
        "contact_information": "+91-98765-00013",
    },
    {
        "property_id": "P016",
        "property_name": "Haibowal Kalan - 1BHK",
        "property_type": "Apartment",
        "location": "Ludhiana",
        "price_inr": 1900000,
        "bedrooms": 1,
        "bathrooms": 1,
        "area_sqft": 480,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security",
        "possession_status": "Ready to Move",
        "description": "Entry-level 1BHK apartment ideal for first-time buyers and rental investors, close to main transit routes.",
        "contact_information": "+91-98765-00014",
    },
    {
        "property_id": "P017",
        "property_name": "Kapurthala Road Residency - 2BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 3500000,
        "bedrooms": 2,
        "bathrooms": 1,
        "area_sqft": 800,
        "furnishing": "Unfurnished",
        "amenities": "Parking, Security, Water Tank, Open Terrace",
        "possession_status": "Ready to Move",
        "description": "Budget-friendly ground-floor 2BHK flat on Kapurthala Road with easy connectivity to LPU campus.",
        "contact_information": "+91-98765-00015",
    },
    {
        "property_id": "P018",
        "property_name": "Nawanshahr Township - 3BHK",
        "property_type": "Apartment",
        "location": "Nawanshahr",
        "price_inr": 4100000,
        "bedrooms": 3,
        "bathrooms": 2,
        "area_sqft": 1250,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Parking, Security, Garden",
        "possession_status": "Under Construction (Expected September 2027)",
        "description": "Spacious 3BHK apartment in an emerging Nawanshahr residential township with landscaped green belt.",
        "contact_information": "+91-98765-00016",
    },
    {
        "property_id": "P019",
        "property_name": "Adampur Enclave - 4BHK House",
        "property_type": "Independent House",
        "location": "Adampur",
        "price_inr": 8200000,
        "bedrooms": 4,
        "bathrooms": 3,
        "area_sqft": 2600,
        "furnishing": "Semi-Furnished",
        "amenities": "Private Garden, Garage, Inverter, Modular Kitchen, Solar Water Heater",
        "possession_status": "Ready to Move",
        "description": "Spacious 4BHK independent house in developing Adampur near Adampur Airport with front courtyard and private garage.",
        "contact_information": "+91-98765-00017",
    },
    {
        "property_id": "P020",
        "property_name": "Lohara Heights - 2BHK",
        "property_type": "Apartment",
        "location": "Ludhiana",
        "price_inr": 4300000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 880,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Gym, Parking, Security, Kids Play Area",
        "possession_status": "Ready to Move",
        "description": "Family-oriented 2BHK flat in Lohara featuring kids play zone, senior citizen seating park, and 24-hour power backup.",
        "contact_information": "+91-98765-00018",
    },
    {
        "property_id": "P021",
        "property_name": "LPU Road Premium - 2BHK",
        "property_type": "Apartment",
        "location": "Phagwara",
        "price_inr": 4000000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 920,
        "furnishing": "Semi-Furnished",
        "amenities": "Lift, Security, Parking, Gym, Study Room",
        "possession_status": "Ready to Move",
        "description": "Modern 2BHK flat on LPU Road with dedicated study nook, gym, and gated security. Ideal for families or faculty.",
        "contact_information": "+91-98765-00019",
    },
    {
        "property_id": "P022",
        "property_name": "Jalandhar Heights Tower A - 2BHK",
        "property_type": "Apartment",
        "location": "Jalandhar",
        "price_inr": 6200000,
        "bedrooms": 2,
        "bathrooms": 2,
        "area_sqft": 1100,
        "furnishing": "Fully Furnished",
        "amenities": "Gym, Pool, Sky Lounge, 24/7 Concierge, Smart Security",
        "possession_status": "Ready to Move",
        "description": "Luxury furnished 2BHK residence in Jalandhar Heights Tower A with sky lounge access and smart security.",
        "contact_information": "+91-98765-00020",
    },
    {
        "property_id": "P023",
        "property_name": "Phagwara Meadow Villa - 3BHK",
        "property_type": "Villa",
        "location": "Phagwara",
        "price_inr": 11200000,
        "bedrooms": 3,
        "bathrooms": 3,
        "area_sqft": 2400,
        "furnishing": "Semi-Furnished",
        "amenities": "Private Lawn, Covered Parking, Clubhouse Access, Solar Power, Security",
        "possession_status": "Ready to Move",
        "description": "Modern 3BHK duplex villa in a gated Phagwara enclave featuring private front lawn and clubhouse access.",
        "contact_information": "+91-98765-00021",
    },
    {
        "property_id": "P024",
        "property_name": "GT Road Heritage House - 3BHK",
        "property_type": "Independent House",
        "location": "Jalandhar",
        "price_inr": 10500000,
        "bedrooms": 3,
        "bathrooms": 3,
        "area_sqft": 2300,
        "furnishing": "Semi-Furnished",
        "amenities": "Private Terrace, Car Porch, Modular Kitchen, Inverter",
        "possession_status": "Ready to Move",
        "description": "Well-maintained 3BHK independent house off GT Road, Jalandhar with spacious terrace and dedicated car porch.",
        "contact_information": "+91-98765-00022",
    },
]

SAMPLE_CUSTOMERS_DATA = [
    {
        "customer_id": "C001",
        "name": "Rajesh Kumar",
        "phone": "+91-98100-11111",
        "email": "rajesh.kumar@example.com",
        "budget_inr": 5000000,
        "preferred_location": "Phagwara",
        "property_type": "Apartment",
        "bedrooms": 2,
        "timeline": "3 months",
        "notes": "Interested in Ready to Move properties. Has home loan pre-approval.",
        "lead_status": "warm",
    },
    {
        "customer_id": "C002",
        "name": "Priya Sharma",
        "phone": "+91-98200-22222",
        "email": "priya.sharma@example.com",
        "budget_inr": 15000000,
        "preferred_location": "Ludhiana",
        "property_type": "Villa",
        "bedrooms": 3,
        "timeline": "2 months",
        "notes": "Looking for villa with ground-floor master suite for family with elderly parents.",
        "lead_status": "qualified",
    },
    {
        "customer_id": "C003",
        "name": "Amit Verma",
        "phone": "+91-98300-33333",
        "email": "amit.verma@example.com",
        "budget_inr": 18000000,
        "preferred_location": "Jalandhar",
        "property_type": "Villa",
        "bedrooms": 4,
        "timeline": "1 month",
        "notes": "Looking for luxury 4BHK villa with private pool in Model Town.",
        "lead_status": "qualified",
    },
    {
        "customer_id": "C004",
        "name": "Sunita Devi",
        "phone": "+91-98400-44444",
        "email": "sunita.devi@example.com",
        "budget_inr": 2500000,
        "preferred_location": "Phagwara",
        "property_type": "Apartment",
        "bedrooms": 1,
        "timeline": "Flexible",
        "notes": "Budget-conscious first-time buyer. Needs home loan guidance.",
        "lead_status": "hot",
    },
    {
        "customer_id": "C005",
        "name": "Gurpreet Singh",
        "phone": "+91-98500-55555",
        "email": "gurpreet.singh@example.com",
        "budget_inr": 6500000,
        "preferred_location": "Phagwara",
        "property_type": "Apartment",
        "bedrooms": 3,
        "timeline": "2 months",
        "notes": "NRI buyer looking for 3BHK investment apartment near LPU.",
        "lead_status": "qualified",
    },
]

COMPANY_KNOWLEDGE_TEXT = """====================================================================
DREAMHOME REALTY - COMPANY KNOWLEDGE DOCUMENT
[FICTIONAL DEMONSTRATION DATA - For FortivexAI Challenge Only]
====================================================================

IMPORTANT NOTICE: All properties, prices, people, and details in
this document are fictional and created solely for demonstration
purposes. No legal guarantees, statutory approvals, or financial
guarantees are made or implied.

====================================================================
SECTION 1: COMPANY INTRODUCTION
====================================================================

About DreamHome Realty:
DreamHome Realty is a fictional residential real estate consultancy
based in Punjab, India. Our tagline is "Your Dream Home, Our Promise."

We help customers explore residential properties across Phagwara,
Jalandhar, Ludhiana, Nawanshahr, and Adampur in Punjab.

Our Services:
- Residential property discovery and consultation
- Guided property site visits and tours
- Home loan coordination and documentation checklists
- Residential investment comparisons
- Step-by-step purchase coordination

Cities Covered: Phagwara, Jalandhar, Ludhiana, Nawanshahr, Adampur
Total Listed Fictional Properties: 24 residential properties

====================================================================
SECTION 2: PROPERTY PORTFOLIO & PRICES OVERVIEW
====================================================================

We currently list fictional properties across three categories:

APARTMENTS:
- 1 BHK: Rs. 19 lakh (Haibowal Kalan, Ludhiana) to Rs. 22 lakh (Lotus Heights, Phagwara)
- 2 BHK: Rs. 35 lakh (Kapurthala Road Residency, Phagwara) to Rs. 62 lakh (Jalandhar Heights Tower A, Jalandhar)
- 3 BHK: Rs. 41 lakh (Nawanshahr Township, Nawanshahr) to Rs. 98 lakh (Sarabha Nagar Premium, Ludhiana)

INDEPENDENT HOUSES:
- 3 BHK: Rs. 1.05 crore (GT Road Heritage House, Jalandhar)
- 4 BHK: Rs. 82 lakh (Adampur Enclave, Adampur) to Rs. 95 lakh (Royal Enclave, Phagwara)

VILLAS:
- 3 BHK: Rs. 1.12 crore (Phagwara Meadow Villa, Phagwara) to Rs. 1.45 crore (BRS Nagar Signature Villa, Ludhiana)
- 4 BHK: Rs. 1.80 crore (Model Town Luxury Villa, Jalandhar)

HIGHLIGHTED LISTINGS:
1. Sunrise Apartments, Phagwara
   - 2 BHK at Rs. 45 lakh (950 sqft) | 3 BHK at Rs. 65 lakh (1350 sqft)
   - Ready to Move | Semi-Furnished
   - Amenities: Lift, Power Backup, Parking, Security, Gym (3BHK adds Clubhouse)

2. LPU Road Premium, Phagwara
   - 2 BHK at Rs. 40 lakh (920 sqft) | Ready to Move | Semi-Furnished
   - Amenities: Lift, Security, Parking, Gym, Study Room

3. Green Valley Homes, Phagwara
   - 2 BHK at Rs. 38 lakh (870 sqft) | 3 BHK at Rs. 52 lakh (1200 sqft)
   - Under Construction | Expected Possession: June 2027

4. Shivalik Residency, Jalandhar
   - 3 BHK at Rs. 75 lakh (1450 sqft) | Ready to Move | Semi-Furnished
   - Amenities: Swimming Pool, Gym, Clubhouse, 24/7 Security, Power Backup

5. Model Town Luxury Villa, Jalandhar
   - 4 BHK Villa at Rs. 1.80 crore (3500 sqft) | Ready to Move | Fully Furnished
   - Amenities: Private Pool, Landscaped Garden, Double Garage, Home Theatre, Smart Home

6. Sarabha Nagar Premium, Ludhiana
   - 3 BHK at Rs. 98 lakh (1750 sqft) | Ready to Move | Fully Furnished
   - Amenities: Gym, Swimming Pool, Clubhouse, Concierge, Valet Parking

7. BRS Nagar Signature Villa, Ludhiana
   - 3 BHK Villa at Rs. 1.45 crore (2800 sqft) | Ready to Move | Semi-Furnished
   - Amenities: Private Garden, Garage, Solar Power, RO Water System

====================================================================
SECTION 3: AMENITIES BY PROPERTY TIER
====================================================================

STANDARD AMENITIES:
- 24/7 Security / Gated Entry
- Dedicated Car Parking
- Water Supply / Storage
- Power Backup / Inverter Support

MID-RANGE / PREMIUM AMENITIES:
- Gymnasium and Fitness Center
- Lift / Elevator
- Clubhouse and Community Hall
- Landscaped Garden / Park and Kids Play Area

LUXURY / VILLA AMENITIES:
- Swimming Pool or Private Pool
- Smart Home Controls
- Concierge & Valet Support (select towers)
- Private Lawn, Home Theatre, Solar Power

====================================================================
SECTION 4: BOOKING AND VIEWING PROCEDURES
====================================================================

HOW TO SCHEDULE A PROPERTY VISIT:
1. Request a visit with our AI sales assistant or support line.
2. Select the property or shortlist of properties you wish to inspect.
3. Choose an available date and time slot during business hours.
4. Confirm your booking to receive a confirmation code (e.g., DH-XXXXXX).
5. A DreamHome Realty consultant meets you at the property for a 60-minute tour.
6. Site visits carry zero obligation or visit fee.

PROPERTY VISIT TIMINGS (Asia/Kolkata):
- Monday to Saturday: 9:00 AM to 6:00 PM
- Sunday: Closed for regular walk-ins (special arrangements only)
- Minimum advance notice: 2 hours before the requested slot

GENERAL PURCHASE STEPS (ILLUSTRATIVE):
1. Shortlist property and complete site visit
2. Submit an Expression of Interest (EOI)
3. Pay an initial booking token as agreed in writing
4. Review and sign the sale agreement
5. Arrange home loan (if applicable) and complete registration

COMMON DOCUMENTATION CHECKLIST:
- Government-issued ID proof (Aadhaar / PAN / Passport)
- Current address proof
- Income proof (salary slips / ITR if applying for a home loan)
- Recent bank statements

====================================================================
SECTION 5: PAYMENT OPTIONS
====================================================================

ILLUSTRATIVE PAYMENT MODES:
- Bank transfer / RTGS / NEFT
- Home loan financing through partner banks
- Milestone-linked schedules for under-construction units

ILLUSTRATIVE BANK OPTIONS (NO LOAN APPROVAL GUARANTEE):
- State Bank of India, HDFC Bank, ICICI Bank, Axis Bank, Punjab National Bank
- Typical residential home loan terms vary by applicant eligibility,
  credit profile, and prevailing bank interest rates. Customers must
  confirm exact rates, fees, and eligibility directly with the lender.

====================================================================
SECTION 6: OFFICE HOURS AND APPOINTMENT POLICIES
====================================================================

FICTIONAL OFFICE ADDRESS:
DreamHome Realty, SCO 45, Main Market, Phagwara, Punjab 144401

CONTACT CHANNELS (FICTIONAL):
- Toll-Free Support: +91-18001-00000
- General Email: info@dreamhomerealty.example
- Escalations: manager@dreamhomerealty.example

OFFICE & APPOINTMENT HOURS (IST / Asia/Kolkata):
- Monday to Saturday: 9:00 AM to 6:00 PM
- Sunday: Closed
- Standard appointment duration: 60 minutes

APPOINTMENT RULES:
- Appointments must be booked at least 2 hours in advance.
- Double booking of the same time slot is blocked automatically.
- Rescheduling or cancellation is free with at least 2 hours notice.
- Please arrive within 15 minutes of your scheduled time.

====================================================================
SECTION 7: FREQUENTLY ASKED QUESTIONS (FAQ)
====================================================================

Q: Are there any site visit charges?
A: No. Guided property site visits arranged through DreamHome Realty are free.

Q: Does DreamHome Realty provide legal or financial guarantees?
A: No. DreamHome Realty provides consultation and coordination only.
   Customers should independently verify all property titles, statutory
   registrations, tax liabilities, and bank loan terms with qualified
   legal and financial advisors before making any payment.

Q: What is the possession timeline for under-construction properties?
A: In this demonstration portfolio, Green Valley Homes (Phagwara) lists
   an expected possession of June 2027, and Nawanshahr Township lists
   September 2027. Always verify official project schedules independently.

Q: Can NRI buyers inquire about properties?
A: Yes. NRI buyers can schedule consultations and explore properties.
   Final transactions require compliance with applicable RBI/FEMA rules
   and independent legal verification.

Q: Is there a brokerage fee?
A: Standard demo consultation assumes a 2% brokerage on completed sale
   transactions, with zero fee for initial inquiries or site visits.

Q: How are maintenance charges handled?
A: Monthly society maintenance varies by building and amenities
   (typically Rs. 1,500 to Rs. 5,000 per month in this demo dataset).

====================================================================
SECTION 8: REFUND AND CANCELLATION POLICIES
====================================================================

SITE VISIT CANCELLATION:
- Site visit appointments may be cancelled or rescheduled at no charge.
- Please cancel in advance via the Appointments page or support line.

BOOKING CANCELLATION GUIDELINES (DEMONSTRATION ONLY):
- Within 7 days of booking: Full refund of initial booking token (demo guideline).
- 8 to 30 days: 50% refund of booking token.
- After 30 days or for under-construction units: Governed strictly by
  the signed developer/seller agreement.

====================================================================
SECTION 9: CUSTOMER SUPPORT
====================================================================

- 24/7 AI Assistant: Available through the DreamHome Realty web portal
- Phone Support: +91-18001-00000 (Mon-Sat, 9:00 AM - 6:00 PM IST)
- Email Support: info@dreamhomerealty.example
- Escalations: manager@dreamhomerealty.example (48-business-hour target)

====================================================================
END OF COMPANY KNOWLEDGE DOCUMENT
[FICTIONAL DEMONSTRATION DATA - FortivexAI Challenge]
====================================================================
"""


def write_properties_csv() -> Path:
    """Write properties.csv deterministically."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "property_id", "property_name", "property_type", "location",
        "price_inr", "bedrooms", "bathrooms", "area_sqft", "furnishing",
        "amenities", "possession_status", "description", "contact_information",
    ]
    with open(config.PROPERTIES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(PROPERTIES_DATA)
    logger.info(f"Generated {config.PROPERTIES_CSV} ({len(PROPERTIES_DATA)} rows)")
    return config.PROPERTIES_CSV


def write_knowledge_txt() -> Path:
    """Write company_knowledge.txt deterministically."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    config.KNOWLEDGE_TXT.write_text(COMPANY_KNOWLEDGE_TEXT, encoding="utf-8")
    logger.info(f"Generated {config.KNOWLEDGE_TXT} ({len(COMPANY_KNOWLEDGE_TEXT)} chars)")
    return config.KNOWLEDGE_TXT


def write_sample_customers_csv() -> Path:
    """Write sample_customers.csv deterministically."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "customer_id", "name", "phone", "email", "budget_inr",
        "preferred_location", "property_type", "bedrooms", "timeline",
        "notes", "lead_status",
    ]
    with open(config.SAMPLE_CUSTOMERS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(SAMPLE_CUSTOMERS_DATA)
    logger.info(f"Generated {config.SAMPLE_CUSTOMERS_CSV} ({len(SAMPLE_CUSTOMERS_DATA)} rows)")
    return config.SAMPLE_CUSTOMERS_CSV


def validate_properties_csv() -> bool:
    """Validate that properties.csv exists, has required columns, and mixes types."""
    required_columns = [
        "property_id", "property_name", "property_type", "location",
        "price_inr", "bedrooms", "bathrooms", "area_sqft", "furnishing",
        "amenities", "possession_status", "description", "contact_information",
    ]
    if not config.PROPERTIES_CSV.exists():
        logger.error(f"properties.csv not found at {config.PROPERTIES_CSV}")
        return False

    with open(config.PROPERTIES_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        rows = list(reader)

    missing = [col for col in required_columns if col not in columns]
    if missing:
        logger.error(f"Missing columns in properties.csv: {missing}")
        return False

    if len(rows) < 20:
        logger.error(f"Expected >= 20 properties, found {len(rows)}")
        return False

    ids = [r["property_id"] for r in rows]
    if len(ids) != len(set(ids)):
        logger.error("Duplicate property_id found in properties.csv")
        return False

    types = {r["property_type"] for r in rows}
    for expected in ("Apartment", "Independent House", "Villa"):
        if expected not in types:
            logger.error(f"Expected property_type '{expected}' missing from properties.csv")
            return False

    logger.info(f"properties.csv valid: {len(rows)} properties across {sorted(types)}")
    return True


def validate_knowledge_txt() -> bool:
    """Validate company knowledge document."""
    if not config.KNOWLEDGE_TXT.exists():
        logger.error(f"company_knowledge.txt not found at {config.KNOWLEDGE_TXT}")
        return False

    text = config.KNOWLEDGE_TXT.read_text(encoding="utf-8")
    if len(text) < 2000:
        logger.error("company_knowledge.txt is unexpectedly short.")
        return False

    required_sections = ["COMPANY", "PROPERTY", "BOOKING", "PAYMENT", "FAQ", "REFUND", "SUPPORT"]
    for section in required_sections:
        if section not in text.upper():
            logger.error(f"Required section '{section}' missing from knowledge base.")
            return False

    logger.info(f"company_knowledge.txt valid: {len(text)} characters")
    return True


def validate_sample_customers() -> bool:
    """Validate sample customers CSV."""
    if not config.SAMPLE_CUSTOMERS_CSV.exists():
        logger.error(f"sample_customers.csv not found at {config.SAMPLE_CUSTOMERS_CSV}")
        return False

    with open(config.SAMPLE_CUSTOMERS_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if len(rows) < 5:
        logger.error(f"Expected >= 5 sample customers, found {len(rows)}")
        return False

    logger.info(f"sample_customers.csv valid: {len(rows)} customers")
    return True


def initialize_database() -> bool:
    """Initialize the SQLite database."""
    try:
        db.init_database()
        logger.info(f"Database initialized at {config.DATABASE_PATH}")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False


def load_sample_customers_to_db() -> int:
    """Load sample customers into the database idempotently."""
    if not config.SAMPLE_CUSTOMERS_CSV.exists():
        return 0

    count = 0
    with open(config.SAMPLE_CUSTOMERS_CSV, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing = db.find_customer_by_phone(row.get("phone", ""))
            if not existing and row.get("email"):
                existing = db.find_customer_by_email(row["email"])
            if existing:
                continue

            try:
                budget = int(row["budget_inr"]) if row.get("budget_inr") else None
                bedrooms = int(row["bedrooms"]) if row.get("bedrooms") else None
                customer_id = db.create_customer({
                    "name": row.get("name"),
                    "phone": row.get("phone"),
                    "email": row.get("email"),
                    "budget_max": budget,
                    "preferred_location": row.get("preferred_location"),
                    "property_type": row.get("property_type"),
                    "bedrooms": bedrooms,
                    "purchase_timeline": row.get("timeline"),
                    "notes": row.get("notes"),
                })

                profile = CustomerProfile(
                    name=row.get("name"),
                    phone=row.get("phone"),
                    email=row.get("email"),
                    budget_max=budget,
                    preferred_location=row.get("preferred_location"),
                    property_type=row.get("property_type"),
                    bedrooms=bedrooms,
                    purchase_timeline=row.get("timeline"),
                )
                qualification = lq.score_lead(profile)

                db.create_lead(customer_id, {
                    "lead_score": qualification.lead_score,
                    "lead_status": qualification.lead_status.value,
                    "sentiment": "neutral",
                    "score_budget": qualification.score_budget,
                    "score_location": qualification.score_location,
                    "score_property_type": qualification.score_property_type,
                    "score_timeline": qualification.score_timeline,
                    "score_contact": qualification.score_contact,
                    "score_interest": qualification.score_interest,
                    "recommended_action": qualification.recommended_action,
                })
                count += 1
            except Exception as e:
                logger.warning(f"Could not load customer {row.get('name')}: {e}")

    logger.info(f"Loaded {count} new sample customers to database")
    return count


def generate_all(load_db: bool = True) -> bool:
    """Create all dataset files, validate them, and optionally populate SQLite."""
    write_properties_csv()
    write_knowledge_txt()
    write_sample_customers_csv()

    ok = (
        validate_properties_csv()
        and validate_knowledge_txt()
        and validate_sample_customers()
    )

    if ok and load_db:
        ok = initialize_database()
        if ok:
            load_sample_customers_to_db()
    return ok


def main() -> bool:
    """Run the complete dataset generation and validation."""
    logger.info("=" * 60)
    logger.info("DreamHome Realty - Dataset Generation & Validation")
    logger.info("=" * 60)

    all_ok = generate_all(load_db=True)

    if all_ok:
        logger.info("All datasets created and validated successfully!")
        logger.info(f"  Properties: {config.PROPERTIES_CSV}")
        logger.info(f"  Knowledge:  {config.KNOWLEDGE_TXT}")
        logger.info(f"  Customers:  {config.SAMPLE_CUSTOMERS_CSV}")
        logger.info(f"  Database:   {config.DATABASE_PATH}")
    else:
        logger.error("Dataset generation or validation failed.")

    return all_ok


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
