# El Pais Opinion Scraper

Scrapes the Opinion section of El País and runs the tests across multiple browsers using BrowserStack.

# Overview

The script visits El País in Spanish, pulls the first 5 articles from the Opinion section, grabs the title, content and cover image for each one, then translates the titles to English. It also checks if any word shows up more than twice across all the titles combined.

Once that works locally, the same script runs across 5 browsers and devices at the same time on BrowserStack.

# Devices used

- Chrome — Windows 11
- Firefox — macOS Ventura  
- Edge — Windows 10
- Chrome — Samsung Galaxy S23 (real device)
- Safari — iPhone 14 (real device)

# Getting started

Install the required packages:

pip install -r requirements.txt


Create a `.env` file and add your BrowserStack credentials:

BROWSERSTACK_USERNAME=your_username
BROWSERSTACK_ACCESS_KEY=your_access_key


# How to run

Test it locally first:

python elpais_scraper.py --local


Then run on BrowserStack:

python elpais_scraper.py --browserstack

# Notes

Translation works out of the box with no API key needed. If you want to use RapidAPI or Google Cloud Translate instead, just add the key to your `.env` file and the script will pick it up automatically.
