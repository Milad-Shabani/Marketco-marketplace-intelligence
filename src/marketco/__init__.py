"""
MarketCo CRM & Operations Intelligence
======================================
An end-to-end analytics platform for a fictional large online
marketplace company, "MarketCo Inc." (modeled conceptually on large regional
e-commerce marketplaces such as Digikala - a multi-seller platform
with its own warehouses, delivery network, and a Microsoft Dynamics
365-style CRM backbone for managing sellers, leads, sales pipeline,
and customer support).

Two analytical products sit on top of the same operational data:

  1. **Operations forecasting** - daily order volume / GMV, including
     the marketplace's own recurring mega-sale events (a "Black
     Friday"-style campaign, a Nowruz shopping season, a mid-year
     mega sale, and a Yalda-night sale), forecast with a global
     LightGBM quantile model.
  2. **CRM analytics** - a Dynamics 365-style entity model (Leads,
     Opportunities, Accounts, Contacts, Cases, Activities) feeding a
     customer-churn classifier and RFM-based customer segmentation.

DATA NOTE: All company, seller, warehouse, and customer/transaction
data in this repository is **synthetically generated** for
portfolio/demo purposes. No real marketplace's sales, customer, or
CRM data is used or implied.
"""

__version__ = "1.0.0"
