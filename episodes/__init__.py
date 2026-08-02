"""Episode definitions for testbed workflows.

Each module defines one workflow's episode: which bus messages are
events, how participants are recognized, and the completion pass that
joins late records (docs/agentic-workflow-view.md). The episode
builder agent arms every definition listed here.
"""

from .prompt_processing import PromptProcessingEpisodes
from .stf_datataking import StfDatatakingEpisodes

ALL_DEFINITIONS = [PromptProcessingEpisodes, StfDatatakingEpisodes]
