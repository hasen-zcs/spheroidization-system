
from abc import ABC, abstractmethod


class ReviewRepository(ABC):

    @abstractmethod
    def save(self, review):
        pass

    @abstractmethod
    def get_by_record_id(self, record_id):
        pass