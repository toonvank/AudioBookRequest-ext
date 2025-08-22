from abc import ABC, abstractmethod
from typing import Any

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.indexers.configuration import Configurations
from app.internal.models import BookRequest, ProwlarrSource


class SessionContainer(BaseModel, arbitrary_types_allowed=True):
    session: Session
    client_session: ClientSession


class AbstractIndexer[T: Configurations](ABC):
    name: str

    @staticmethod
    @abstractmethod
    async def get_configurations(
        container: SessionContainer,
    ) -> T:
        """
        Returns a list of configuration options that will be configurable on the frontend.
        This should not execute any slow operations.
        """
        pass

    @abstractmethod
    async def is_active(
        self,
        container: SessionContainer,
        configurations: Any,
    ) -> bool:
        """
        Returns true if the indexer is active and can be used.
        """
        pass

    @abstractmethod
    async def setup(
        self,
        request: BookRequest,
        container: SessionContainer,
        configurations: Any,
    ) -> None:
        """
        Called initially when a book request is made.
        Can be used to set up initial settings required
        for the indexer
        Or if the indexer only supports
        a general search feature, a general search can be executed here
        and later used to check against individual sources.
        """
        pass

    @abstractmethod
    async def is_matching_source(
        self, source: ProwlarrSource, container: SessionContainer
    ) -> bool:
        """Given a source from Prowlarr, returns true if that source matches this indexer."""
        pass

    @abstractmethod
    async def edit_source_metadata(
        self, source: ProwlarrSource, container: SessionContainer
    ) -> None:
        """
        Takes a prowlarr source and adds additional metadata to it directly from the indexer.

        This can be used in combiniation with the data from `setup` to match up books more accurately.
        """
        pass
