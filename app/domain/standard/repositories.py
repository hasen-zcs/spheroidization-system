
from abc import ABC, abstractmethod


class StandardRepository(ABC):

    @abstractmethod
    def save(self, standard):
        pass

    @abstractmethod
    def get_current(self):
        pass

    @abstractmethod
    def get_history(self):
        pass