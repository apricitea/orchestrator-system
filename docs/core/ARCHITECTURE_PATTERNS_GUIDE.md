# Architecture Patterns and Refactoring Guide

**Based on SkillsMP Best Practices**

---

## Table of Contents

1. [Architecture Anti-Patterns to Avoid](#architecture-anti-patterns-to-avoid)
2. [Design Patterns for Production](#design-patterns-for-production)
3. [Refactoring Strategies](#refactoring-strategies)
4. [Microservices vs Monolith](#microservices-vs-monolith)
5. [Event-Driven Architecture](#event-driven-architecture)
6. [Dependency Injection](#dependency-injection)
7. [Caching Strategies](#caching-strategies)
8. [Observability Patterns](#observability-patterns)
9. [Refactoring Checklist](#refactoring-checklist)

---

## Architecture Anti-Patterns to Avoid

### 1. Monolithic Functions (God Object)

**Problem**: Single function does too much.

```python
# ❌ BAD - Monolithic function
def process_user_request(user_id):
    # Load user
    user = db.query(f"SELECT * FROM users WHERE id = {user_id}")

    # Validate
    if not user:
        raise Error("User not found")

    # Process payment
    payment = stripe.charge(user.card_token, amount)

    # Send email
    send_email(user.email, "Payment processed")

    # Update database
    db.execute(f"UPDATE users SET paid = true WHERE id = {user_id}")

    return payment
```

**Solution**: Single Responsibility Principle.

```python
# ✅ GOOD - Separated concerns
class UserService:
    def get_user(self, user_id: int) -> User:
        return self.db.query("SELECT * FROM users WHERE id = ?", user_id)

class PaymentService:
    def charge_user(self, user: User, amount: float) -> Payment:
        return self.stripe.charge(user.card_token, amount)

class NotificationService:
    def send_payment_confirmation(self, user: User):
        self.email_sender.send(user.email, "Payment processed")

class OrderProcessor:
    def __init__(
        self,
        user_service: UserService,
        payment_service: PaymentService,
        notification_service: NotificationService
    ):
        self.user_service = user_service
        self.payment_service = payment_service
        self.notification_service = notification_service

    def process_order(self, user_id: int, amount: float) -> Payment:
        user = self.user_service.get_user(user_id)
        payment = self.payment_service.charge_user(user, amount)
        self.notification_service.send_payment_confirmation(user)
        return payment
```

### 2. Global State

**Problem**: Shared mutable state causes bugs.

```python
# ❌ BAD - Global state
database = None

def init_db():
    global database
    database = connect()

def get_user():
    return database.query("SELECT * FROM users")
```

**Solution**: Dependency Injection.

```python
# ✅ GOOD - Dependency injection
class Database:
    def __init__(self, connection_string: str):
        self.connection = connect(connection_string)

class UserRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_users(self):
        return self.db.query("SELECT * FROM users")
```

### 3. Tight Coupling

**Problem**: Hard to test, hard to change.

```python
# ❌ BAD - Tight coupling
class UserManager:
    def create_user(self, email):
        # Directly creates Stripe customer
        stripe.Customer.create(email=email)

        # Directly sends email
        sendgrid.send(email)

        # Directly saves to DB
        db.execute(f"INSERT INTO users (email) VALUES ('{email}')")
```

**Solution**: Interface segregation, dependency inversion.

```python
# ✅ GOOD - Loose coupling
class PaymentProvider(ABC):
    @abstractmethod
    def create_customer(self, email: str) -> str:
        pass

class EmailSender(ABC):
    @abstractmethod
    def send(self, email: str, message: str):
        pass

class UserRepository(ABC):
    @abstractmethod
    def save(self, email: str) -> int:
        pass

class UserManager:
    def __init__(
        self,
        payment_provider: PaymentProvider,
        email_sender: EmailSender,
        user_repo: UserRepository
    ):
        self.payment_provider = payment_provider
        self.email_sender = email_sender
        self.user_repo = user_repo

    def create_user(self, email: str) -> int:
        self.payment_provider.create_customer(email)
        self.email_sender.send(email, "Welcome!")
        return self.user_repo.save(email)
```

---

## Design Patterns for Production

### 1. Repository Pattern

Separate data access logic from business logic.

```python
class UserRepository(ABC):
    """Abstract base for user data access."""

    @abstractmethod
    def find_by_id(self, user_id: int) -> Optional[User]:
        pass

    @abstractmethod
    def find_by_email(self, email: str) -> Optional[User]:
        pass

    @abstractmethod
    def save(self, user: User) -> User:
        pass


class SQLUserRepository(UserRepository):
    """SQL implementation of UserRepository."""

    def __init__(self, db: Database):
        self.db = db

    def find_by_id(self, user_id: int) -> Optional[User]:
        row = self.db.fetch_one(
            "SELECT * FROM users WHERE id = ?",
            (user_id,)
        )
        return User.from_row(row) if row else None

    def find_by_email(self, email: str) -> Optional[User]:
        row = self.db.fetch_one(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        )
        return User.from_row(row) if row else None

    def save(self, user: User) -> User:
        if user.id:
            self.db.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (user.email, user.id)
            )
        else:
            user.id = self.db.insert(
                "INSERT INTO users (email) VALUES (?)",
                (user.email,)
            )
        return user
```

### 2. Factory Pattern

Create objects without specifying exact class.

```python
class DatabaseClientFactory:
    """Factory for creating database clients."""

    @staticmethod
    def create(config: DatabaseConfig) -> DatabaseClient:
        if config.type == "postgresql":
            return PostgreSQLClient(config.url)
        elif config.type == "mysql":
            return MySQLClient(config.url)
        elif config.type == "mongodb":
            return MongoDBClient(config.url)
        else:
            raise ValueError(f"Unknown database type: {config.type}")
```

### 3. Strategy Pattern

Encapsulate interchangeable algorithms.

```python
class CacheStrategy(ABC):
    """Abstract cache strategy."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int):
        pass


class RedisCache(CacheStrategy):
    """Redis-based caching."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def get(self, key: str) -> Optional[Any]:
        value = self.redis.get(key)
        return json.loads(value) if value else None

    def set(self, key: str, value: Any, ttl: int):
        self.redis.setex(key, ttl, json.dumps(value))


class MemoryCache(CacheStrategy):
    """In-memory caching (for testing)."""

    def __init__(self):
        self.cache = {}

    def get(self, key: str) -> Optional[Any]:
        return self.cache.get(key)

    def set(self, key: str, value: Any, ttl: int):
        self.cache[key] = value


class DataService:
    """Service using pluggable cache strategy."""

    def __init__(self, cache: CacheStrategy):
        self.cache = cache

    def get_user(self, user_id: int) -> User:
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            return cached

        user = self.fetch_from_db(user_id)
        self.cache.set(f"user:{user_id}", user, ttl=3600)
        return user
```

### 4. Observer Pattern

Notify subscribers of events.

```python
class EventEmitter:
    """Simple event emitter for pub/sub."""

    def __init__(self):
        self.listeners = defaultdict(list)

    def on(self, event: str, callback: Callable):
        """Subscribe to event."""
        self.listeners[event].append(callback)

    def emit(self, event: str, *args, **kwargs):
        """Publish event."""
        for callback in self.listeners[event]:
            callback(*args, **kwargs)


class UserService:
    def __init__(self):
        self.events = EventEmitter()

    def create_user(self, email: str):
        user = User(email=email)
        self.events.emit("user.created", user)
        return user


# Usage
def send_welcome_email(user):
    send_email(user.email, "Welcome!")

def track_analytics(user):
    analytics.track("user_signup", {"email": user.email})

user_service = UserService()
user_service.events.on("user.created", send_welcome_email)
user_service.events.on("user.created", track_analytics)
```

---

## Refactoring Strategies

### 1. Extract Method

Break large functions into smaller ones.

**Before**:
```python
def process_order(order_id):
    order = db.get_order(order_id)
    if not order.paid:
        payment = stripe.charge(order.amount)
        if payment.success:
            order.paid = True
            order.save()
            email.send(order.user_email, "Order paid")
            return order
    return order
```

**After**:
```python
def process_order(order_id):
    order = db.get_order(order_id)
    if not order.paid:
        payment = charge_order(order)
        if payment.success:
            mark_order_paid(order)
            notify_payment_success(order)
    return order

def charge_order(order):
    return stripe.charge(order.amount)

def mark_order_paid(order):
    order.paid = True
    order.save()

def notify_payment_success(order):
    email.send(order.user_email, "Order paid")
```

### 2. Extract Class

Group related functionality.

**Before**:
```python
class Order:
    def __init__(self, items):
        self.items = items

    def calculate_total(self):
        return sum(i.price for i in self.items)

    def calculate_tax(self):
        return self.calculate_total() * 0.1

    def calculate_shipping(self):
        return 10 if self.calculate_total() < 100 else 0

    def apply_discount(self, code):
        # 50 lines of discount logic
        pass

    def validate_coupon(self, code):
        # 30 lines of validation
        pass
```

**After**:
```python
class Order:
    def __init__(self, items, pricing_calculator):
        self.items = items
        self.pricing = pricing_calculator

    def total(self):
        return self.pricing.calculate_total(self.items)


class PricingCalculator:
    def __init__(self, tax_rate, shipping_threshold):
        self.tax_rate = tax_rate
        self.shipping_threshold = shipping_threshold

    def calculate_total(self, items):
        subtotal = sum(i.price for i in items)
        tax = subtotal * self.tax_rate
        shipping = 10 if subtotal < self.shipping_threshold else 0
        return subtotal + tax + shipping


class DiscountService:
    def apply_discount(self, order, code):
        # Discount logic
        pass

    def validate_coupon(self, code):
        # Validation logic
        pass
```

### 3. Replace Conditional with Polymorphism

**Before**:
```python
def process_payment(payment_type, amount):
    if payment_type == "credit_card":
        return process_credit_card(amount)
    elif payment_type == "paypal":
        return process_paypal(amount)
    elif payment_type == "bank_transfer":
        return process_bank_transfer(amount)
    else:
        raise ValueError("Unknown payment type")
```

**After**:
```python
class PaymentProcessor(ABC):
    @abstractmethod
    def process(self, amount: float) -> PaymentResult:
        pass


class CreditCardProcessor(PaymentProcessor):
    def process(self, amount: float) -> PaymentResult:
        # Credit card logic
        pass


class PayPalProcessor(PaymentProcessor):
    def process(self, amount: float) -> PaymentResult:
        # PayPal logic
        pass


class BankTransferProcessor(PaymentProcessor):
    def process(self, amount: float) -> PaymentResult:
        # Bank transfer logic
        pass


class PaymentProcessorFactory:
    processors = {
        "credit_card": CreditCardProcessor(),
        "paypal": PayPalProcessor(),
        "bank_transfer": BankTransferProcessor(),
    }

    @classmethod
    def get_processor(cls, payment_type: str) -> PaymentProcessor:
        processor = cls.processors.get(payment_type)
        if not processor:
            raise ValueError(f"Unknown payment type: {payment_type}")
        return processor
```

---

## Microservices vs Monolith

### When to Use Monolith

**Good for**:
- Small teams (< 10 developers)
- Simple domain with low complexity
- MVP/prototype phase
- Limited resources

**Structure**:
```
myapp/
├── core/           # Domain models
├── services/       # Business logic
├── repositories/   # Data access
├── api/            # Endpoints
└── tests/          # Tests
```

### When to Use Microservices

**Good for**:
- Large teams (> 20 developers)
- Complex domain with bounded contexts
- Different scaling requirements per service
- Independent deployment cycles

**Structure**:
```
services/
├── user-service/
├── payment-service/
├── order-service/
├── notification-service/
└── api-gateway/
```

### Modular Monolith (Best of Both)

**Structure**:
```
myapp/
├── modules/
│   ├── user/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── repositories.py
│   │   └── api.py
│   ├── payment/
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── repositories.py
│   │   └── api.py
│   └── order/
│       ├── models.py
│       ├── services.py
│       ├── repositories.py
│       └── api.py
├── shared/
│   ├── database.py
│   ├── utils.py
│   └── config.py
└── tests/
```

---

## Event-Driven Architecture

### Using Events for Decoupling

```python
from dataclasses import dataclass
from typing import Callable, List
from enum import Enum


class EventType(Enum):
    USER_CREATED = "user.created"
    ORDER_PLACED = "order.placed"
    PAYMENT_SUCCESS = "payment.success"


@dataclass
class Event:
    type: EventType
    data: dict
    timestamp: datetime


class EventBus:
    def __init__(self):
        self.handlers: Dict[EventType, List[Callable]] = defaultdict(list)

    def subscribe(self, event_type: EventType, handler: Callable):
        self.handlers[event_type].append(handler)

    def publish(self, event: Event):
        for handler in self.handlers[event.type]:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler failed: {e}")


# Usage
event_bus = EventBus()

def send_welcome_email(event: Event):
    user = event.data
    send_email(user["email"], "Welcome!")

def update_analytics(event: Event):
    analytics.track("user_signup", event.data)

event_bus.subscribe(EventType.USER_CREATED, send_welcome_email)
event_bus.subscribe(EventType.USER_CREATED, update_analytics)

# Publish event
event_bus.publish(Event(
    type=EventType.USER_CREATED,
    data={"email": "user@example.com", "id": 123},
    timestamp=datetime.utcnow()
))
```

---

## Dependency Injection

### Manual DI

```python
class Container:
    """Simple DI container."""

    def __init__(self):
        self._singletons = {}
        self._factories = {}

    def register_singleton(self, interface, implementation):
        self._singletons[interface] = implementation

    def register_factory(self, interface, factory):
        self._factories[interface] = factory

    def get(self, interface):
        if interface in self._singletons:
            return self._singletons[interface]

        if interface in self._factories:
            return self._factories[interface]()

        raise ValueError(f"Service not registered: {interface}")


# Setup
container = Container()
container.register_singleton(Database, Database(config.db_url))
container.register_factory(UserRepository, lambda: SQLUserRepository(container.get(Database)))
container.register_factory(UserService, lambda: UserService(container.get(UserRepository)))

# Use
user_service = container.get(UserService)
```

### Using `dependency-injector` Library

```python
from dependency_injector import containers, providers, dependency


class Container(containers.DeclarativeContainer):
    """Application container."""

    config = providers.Configuration()

    database = providers.Singleton(
        Database,
        connection_string=config.db_url
    )

    user_repository = providers.Factory(
        SQLUserRepository,
        db=database
    )

    user_service = providers.Factory(
        UserService,
        user_repo=user_repository
    )
```

---

## Caching Strategies

### 1. Cache-Aside (Lazy Loading)

```python
def get_user(user_id: int) -> User:
    # Try cache first
    cached = cache.get(f"user:{user_id}")
    if cached:
        return cached

    # Cache miss - fetch from DB
    user = db.query("SELECT * FROM users WHERE id = ?", user_id)

    # Store in cache
    cache.set(f"user:{user_id}", user, ttl=3600)

    return user
```

### 2. Write-Through

```python
def save_user(user: User):
    # Write to DB
    db.execute("INSERT INTO users ...", user)

    # Update cache immediately
    cache.set(f"user:{user.id}", user, ttl=3600)
```

### 3. Write-Behind (Async)

```python
def save_user_async(user: User):
    # Update cache immediately
    cache.set(f"user:{user.id}", user, ttl=3600)

    # Queue for async write to DB
    queue.put(("save_user", user))

# Background worker
def worker():
    while True:
        operation, data = queue.get()
        if operation == "save_user":
            db.execute("INSERT INTO users ...", data)
```

### Cache Invalidation

```python
class CacheInvalidator:
    """Invalidate related caches when data changes."""

    def __init__(self, cache):
        self.cache = cache

    def invalidate_user(self, user_id: int):
        patterns = [
            f"user:{user_id}",
            f"user:{user_id}:*",
            f"users:active:*",
        ]
        for pattern in patterns:
            self.cache.delete_pattern(pattern)
```

---

## Observability Patterns

### 1. Structured Logging

```python
from agents.automation.structured_logging import get_structured_logger

logger = get_structured_logger("order_service")

def create_order(user_id: int, items: List[Item]):
    logger.info(
        "Creating order",
        user_id=user_id,
        item_count=len(items),
        total_amount=sum(i.price for i in items)
    )

    order = Order(user_id=user_id, items=items)

    logger.info(
        "Order created",
        order_id=order.id,
        user_id=user_id,
        status=order.status
    )

    return order
```

### 2. Distributed Tracing

```python
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def traced(func):
    """Decorator for distributed tracing."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        request_id = request_id_var.get() or str(uuid.uuid4())

        logger.info(
            f"Entering: {func.__name__}",
            function=func.__name__,
            request_id=request_id
        )

        start = time.time()
        try:
            result = await func(*args, **kwargs)
            duration_ms = (time.time() - start) * 1000

            logger.info(
                f"Exiting: {func.__name__}",
                function=func.__name__,
                request_id=request_id,
                duration_ms=duration_ms,
                success=True
            )

            return result

        except Exception as e:
            duration_ms = (time.time() - start) * 1000

            logger.error(
                f"Error in: {func.__name__}",
                function=func.__name__,
                request_id=request_id,
                duration_ms=duration_ms,
                exception=e
            )

            raise

    return wrapper
```

### 3. Metrics Collection

```python
from agents.automation.structured_logging import get_metrics_collector

metrics = get_metrics_collector()

@traced
async def process_order(order_id: int):
    metrics.increment("orders.processing.started")

    try:
        order = await fetch_order(order_id)

        metrics.record_histogram(
            "orders.amount",
            order.total_amount,
            tags={"currency": order.currency}
        )

        # Process order...

        metrics.increment("orders.processing.success")
        return order

    except Exception as e:
        metrics.increment("orders.processing.error")
        raise
```

---

## Refactoring Checklist

### Code Organization

- [ ] Each module has a single responsibility
- [ ] No circular dependencies
- [ ] Clear separation between layers (models, services, repositories)
- [ ] Dependencies injected, not hardcoded
- [ ] No global mutable state

### Function Design

- [ ] Functions are small (< 50 lines)
- [ ] Functions do one thing
- [ ] Functions have descriptive names
- [ ] Functions have < 4 parameters
- [ ] No flag arguments (boolean parameters)

### Error Handling

- [ ] Specific exceptions, not generic `Exception`
- [ ] Errors are logged with context
- [ ] Error messages are actionable
- [ ] Graceful degradation where possible
- [ ] No silent failures

### Performance

- [ ] No N+1 queries
- [ ] Expensive operations are cached
- [ ] Database indexes on queried fields
- [ ] No unnecessary loops
- [ ] Lazy loading where appropriate

### Security

- [ ] Input validation on all inputs
- [ ] No hardcoded secrets
- [ ] SQL queries use parameters
- [ ] User input is escaped in templates
- [ ] Authentication/authorization checks

### Testing

- [ ] Unit tests for business logic
- [ ] Integration tests for workflows
- [ ] Mocking external dependencies
- [ ] Tests cover edge cases
- [ ] Test coverage > 80%

### Documentation

- [ ] Docstrings on public APIs
- [ ] Complex logic has comments
- [ ] README explains setup
- [ ] API documentation exists
- [ ] Architecture documented

---

**Sources:**
- [Software Architecture Design](https://skillsmp.com/es/skills/vasilyu1983-ai-agents-public-frameworks-shared-skills-skills-software-architecture-design-skill-md)
- [Domain-Driven Design](https://skillsmp.com/skills/bfollington-terma-skills-domain-driven-design-skill-md)
- [ln-363 Architecture Auditor](https://skillsmp.com/zh/skills/levnikolaevich-claude-code-skills-ln-363-architecture-auditor-skill-md)
