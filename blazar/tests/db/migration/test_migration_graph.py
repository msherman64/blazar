# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Static checks on the alembic revision graph.

These validate the migration scripts themselves, without a database.
They exist because ``alembic history`` exits successfully even when a
revision's ``down_revision`` references a revision that does not exist
(e.g. a migration cherry-picked from a tree with a different alembic
history), and because ``alembic upgrade head`` refuses to run when the
graph has more than one head. Both states break
``blazar-db-manage upgrade head`` at deploy time but are otherwise
invisible to the unit suite.
"""

import os

from alembic import config as alembic_config
from alembic import script as alembic_script

from blazar.db import migration
from blazar.tests import TestCase


def _find_alembic_conf():
    """Build an alembic Config for blazar's migration repository."""
    path = os.path.join(
        os.path.abspath(os.path.dirname(migration.__file__)), 'alembic.ini')
    config = alembic_config.Config(path)
    config.attributes['configure_logger'] = False
    return config


class TestMigrationGraph(TestCase):

    def setUp(self):
        super(TestMigrationGraph, self).setUp()
        self.script = alembic_script.ScriptDirectory.from_config(
            _find_alembic_conf())

    def test_single_base_revision(self):
        """Ensure we only have a single base revision.

        There's no good reason for us to have diverging history, so
        validate that only one base revision exists. If this fails for
        your change, look for migrations that do not have a 'Revises'
        line in them.
        """
        self.assertEqual(1, len(self.script.get_bases()))

    def test_single_head_revision(self):
        """Ensure we only have a single head revision.

        There's no good reason for us to have diverging history, so validate
        that only one head revision exists. This will prevent merge conflicts
        adding additional head revision points. If this fails for your change,
        look for migrations with the same 'revises' line in them.
        """
        heads = self.script.get_heads()
        self.assertEqual(
            1, len(heads), 'expected a single head, found: %s'
            % ', '.join(heads))

    def test_no_dangling_down_revisions(self):
        """Ensure every down_revision resolves to a known revision.

        A dangling down_revision usually also fails
        test_single_head_revision, but for merge revisions (multiple
        parents) the head count does not change when one parent is
        missing, so check the references explicitly.
        """
        known = {sc.revision
                 for sc in self.script.walk_revisions('base', 'heads')}
        self.assertGreater(len(known), 0)
        dangling = []
        for sc in self.script.walk_revisions('base', 'heads'):
            downs = sc.down_revision
            if downs is None:
                continue
            if isinstance(downs, str):
                downs = (downs,)
            for down in downs:
                if down not in known:
                    dangling.append('%s revises unknown %s'
                                    % (sc.revision, down))
        self.assertEqual([], dangling)