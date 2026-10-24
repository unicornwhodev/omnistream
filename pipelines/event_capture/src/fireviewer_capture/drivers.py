"""Renderer contract; no Omniverse import is needed to test orchestration."""
from abc import ABC,abstractmethod
from dataclasses import dataclass


@dataclass
class RenderBatch:
    frames:dict
    render_wall_s:float
    gpu_render_execution_s:float|None=None
    gpu_timing_source:str|None=None


class RenderDriver(ABC):
    async def prepare_batch(self,handles,contexts,config):
        """Optional validated scene residency hook, before any product is enabled."""
        return None
    descriptor={"native_omniverse":False,"kind":"abstract"}
    @abstractmethod
    async def initialize(self,config):...
    @abstractmethod
    async def create_product(self,camera,config):...
    @abstractmethod
    def set_updates(self,handle,enabled):...
    @abstractmethod
    def camera_metadata(self,camera,config):...
    @abstractmethod
    async def trigger(self,handles,contexts,config)->RenderBatch:...
    @abstractmethod
    async def destroy_product(self,handle):...
    async def close(self):pass
