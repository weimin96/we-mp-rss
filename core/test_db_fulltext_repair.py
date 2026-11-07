"""Regression: a metadata-only article must accept later fulltext recovery."""

import unittest
from unittest.mock import Mock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Db
from core.models.article import Article
from core.wx.model.weread_mp import MpsWereadMP


class FulltextRepairTests(unittest.TestCase):
    def test_pending_article_is_repaired_by_review_id_without_list_query(self):
        engine = create_engine("sqlite://")
        Article.__table__.create(engine)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            session.add(Article(
                id="100-100_review", mp_id="MP_WXS_100",
                title="Pending", url="https://example.test/pending",
                content=None, has_content=0, publish_time=12345, status=1,
            ))
            session.commit()

        collector = object.__new__(MpsWereadMP)
        collector._get_mp_content = Mock(return_value="<p>Restored full text</p>")
        with patch("core.db.DB.get_session", new=session_factory):
            self.assertEqual(collector.repair_one_missing_fulltext("MP_WXS_100"), 1)
            self.assertEqual(collector.repair_one_missing_fulltext("MP_WXS_100"), 0)
        collector._get_mp_content.assert_called_once_with("MP_WXS_100_review")
        with session_factory() as session:
            article = session.get(Article, "100-100_review")
            self.assertEqual(article.has_content, 1)
            self.assertIn("Restored full text", article.content)
            self.assertIn("Restored full text", article.content_html)

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
