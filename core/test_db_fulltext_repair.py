"""Regression: a metadata-only article must accept later fulltext recovery."""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Db
from core.models.article import Article


class FulltextRepairTests(unittest.TestCase):
    def test_new_fulltext_repairs_incomplete_article_without_losing_metadata(self):
        engine = create_engine("sqlite://")
        Article.__table__.create(engine)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            session.add(Article(
                id="100-100_new", mp_id="MP_WXS_100",
                title="Saved article", url="https://example.test/article",
                content=None, has_content=0, publish_time=12345,
                status=1,
            ))
            session.commit()

        db = Db.__new__(Db)
        db.get_session = session_factory
        db.tag = "fulltext-repair-test"
        recovered = db.add_article({
            "id": "MP_WXS_100_new", "mp_id": "MP_WXS_100",
            "title": "Saved article", "url": "https://example.test/article",
            "content": "<p>Real body with more than a headline</p>",
            "publish_time": 12345,
        })

        self.assertTrue(recovered)
        with session_factory() as session:
            article = session.get(Article, "100-100_new")
            self.assertEqual(article.title, "Saved article")
            self.assertEqual(article.publish_time, 12345)
            self.assertEqual(article.has_content, 1)
            self.assertIn("Real body", article.content)
            self.assertIn("Real body", article.content_html)
            self.assertEqual(session.query(Article).count(), 1)


if __name__ == "__main__":
    unittest.main()
