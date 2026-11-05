"""Explicitly unavailable publishing adapters; no simulated success."""
from typing import Literal
from pydantic import BaseModel, Field

class Draft(BaseModel):
    title: str = Field('',max_length=200)
    description: str = Field('',max_length=20000)
    price: float | None = Field(None,ge=0)
    category: str = ''
    stock: int = Field(1,ge=0)
    sku: list[dict] = Field(default_factory=list)
    images: list[str] = Field(default_factory=list)
    logistics: dict = Field(default_factory=dict)
    platform_fields: dict = Field(default_factory=dict)
    platforms: list[Literal["taobao", "xianyu", "xiaohongshu"]] = Field(default_factory=list)
    source_url: str = ''

class Publisher:
    name = ''
    required = ['title','description','price','category','stock','images','logistics']
    def info(self) -> dict:
        return {'platform':self.name,'status':'暂不支持 · 需要官方授权','required':self.required,
                'authorization':'未配置官方授权','supported':False}
    def validate(self, draft: Draft) -> list[str]:
        d=draft.model_dump()
        return [f'请填写 {k}' for k in self.required if d.get(k) is None or d.get(k)=='' or d.get(k)==[] or d.get(k)=={}]

class TaobaoPublisher(Publisher):
    name='taobao'
class XianyuPublisher(Publisher):
    name='xianyu'
class XiaohongshuPublisher(Publisher):
    name='xiaohongshu'

PUBLISHERS={p.name:p for p in (TaobaoPublisher(),XianyuPublisher(),XiaohongshuPublisher())}
