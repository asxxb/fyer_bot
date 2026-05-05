"""
core/sentiment.py
Headline-based sentiment analysis
using Finnhub + VADER
"""

import requests

from vaderSentiment.vaderSentiment import (
    SentimentIntensityAnalyzer
)

from config import settings

from utils.logger import get_logger

log = get_logger()


class SentimentAnalyzer:

    def __init__(self):

        self.api_key = (
            settings.FINNHUB_API_KEY
        )

        self.analyzer = (
            SentimentIntensityAnalyzer()
        )

    # ---------------------------------------------------
    # NEWS SENTIMENT
    # ---------------------------------------------------

    def get_sentiment(
        self,
        symbol: str
    ) -> float:

        try:

            clean_symbol = (

                symbol
                .replace("-EQ", "")
                .replace(".NS", "")

            )

            # -----------------------------------------
            # Finnhub News Endpoint
            # -----------------------------------------

            url = (
                "https://finnhub.io/api/v1/company-news"
            )

            params = {

                "symbol": clean_symbol,

                "from": "2026-05-01",

                "to": "2026-05-04",

                "token": self.api_key

            }

            response = requests.get(

                url,

                params=params,

                timeout=10

            )

            data = response.json()

            # -----------------------------------------
            # No News
            # -----------------------------------------

            if not data or not isinstance(data, list):

                return 0.0

            scores = []

            # -----------------------------------------
            # Analyze Headlines
            # -----------------------------------------

            for article in data[:10]:

                headline = article.get(
                    "headline",
                    ""
                )

                if headline:

                    score = (

                        self.analyzer
                        .polarity_scores(headline)

                    )["compound"]

                    scores.append(score)

            # -----------------------------------------
            # Average
            # -----------------------------------------

            if not scores:

                return 0.0

            avg_sentiment = (

                sum(scores)

                /

                len(scores)

            )

            return round(
                avg_sentiment,
                2
            )

        except Exception as e:

            log.error(

                f"Sentiment error "
                f"{symbol}: {e}"

            )

            return 0.0