
from abc import ABC, abstractmethod


class SpheroidizationRepository(ABC):

    @abstractmethod
    def save(self, record):
        pass

    @abstractmethod
    def get_by_id(self, record_id):
        pass

    @abstractmethod
    def query(self, query):
        pass