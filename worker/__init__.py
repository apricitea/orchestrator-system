"""
AI Agent Worker Daemon - Always-On Task Processing System

This module provides a continuous worker that:
1. Checks LLM availability and rate limits
2. Processes tasks from Trello/Telegram/PostgreSQL
3. Executes tasks via AI agents
4. Automates git workflow (branch → PR → merge)
5. Handles rate limiting with exponential backoff
"""

__version__ = "1.0.0"
