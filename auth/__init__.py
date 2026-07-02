"""
DID身份鉴权模块

基于DID的操作签名鉴权，为MemGuard提供"谁可以干什么"的管控能力。
"""

from .did_auth import DIDAuthenticator

__all__ = ['DIDAuthenticator']
