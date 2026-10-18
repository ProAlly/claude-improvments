# Scaffolding the NestJS + MongoDB project

## Base project

```bash
npx @nestjs/cli new <project-name>
```

This already gives TypeScript, Jest, ESLint, and Prettier. Don't
re-initialize any of those — build on what's there.

## Core dependencies

```bash
npm install @nestjs/mongoose mongoose @nestjs/config class-validator class-transformer
npm install @nestjs/cache-manager cache-manager
npm install --save-dev husky mongodb-memory-server
```

## Layering: controller → service → repository

Keep the same three layers as any SOLID backend, expressed with Nest's own
tools:

- **Controller** — parses the request (DTOs, validated by
  `class-validator` through a global `ValidationPipe`), calls a service,
  shapes the response. No business logic, no direct Mongoose access.
- **Service** — business logic and orchestration. Depends on a
  **repository interface**, not a concrete `Model<T>`.
- **Repository** — the only place that imports the Mongoose `Model` and
  talks to MongoDB.

The service-depends-on-an-interface part is what makes this a real
Dependency Inversion boundary instead of decoration. Define an abstract
token and interface, then bind the concrete implementation in the module:

```ts
// users.repository.ts
export interface UsersRepository {
  findById(id: string): Promise<User | null>;
  create(data: CreateUserData, session?: ClientSession): Promise<User>;
}
export const USERS_REPOSITORY = Symbol('USERS_REPOSITORY');

@Injectable()
export class MongooseUsersRepository implements UsersRepository {
  constructor(@InjectModel(User.name) private readonly model: Model<User>) {}
  findById(id: string) {
    return this.model.findById(id).exec();
  }
  create(data: CreateUserData, session?: ClientSession) {
    return this.model.create([data], { session }).then(([doc]) => doc);
  }
}
```

```ts
// users.module.ts
@Module({
  imports: [MongooseModule.forFeature([{ name: User.name, schema: UserSchema }])],
  providers: [
    UsersService,
    { provide: USERS_REPOSITORY, useClass: MongooseUsersRepository },
  ],
})
export class UsersModule {}
```

`UsersService` then depends on `@Inject(USERS_REPOSITORY) private readonly repo: UsersRepository`
— it can be unit-tested with a fake repository, no database required. This
is what makes the TDD loop in
[references/tooling-and-testing.md](references/tooling-and-testing.md) fast
for the unit layer.

Don't build this interface indirection for every trivial CRUD module on
day one if the project is genuinely small — introduce it where a module
actually has business logic worth isolating, or where transactions are
involved. A single-collection module with no logic beyond "save this
document" doesn't need the ceremony; over-applying this pattern
everywhere is the over-engineering the main workflow warns against.

## MongoDB connection and config

```ts
// app.module.ts
MongooseModule.forRootAsync({
  imports: [ConfigModule],
  inject: [ConfigService],
  useFactory: (config: ConfigService) => ({
    uri: config.getOrThrow<string>('MONGODB_URI'),
  }),
});
```

Validate required env vars at boot (a Joi schema passed to
`ConfigModule.forRoot({ validationSchema })`, or a `class-validator`-based
config class) so a missing `MONGODB_URI` fails immediately on startup
instead of on the first request that touches the database.

## Transactions and cache

See [references/mongodb-transactions-and-cache.md](references/mongodb-transactions-and-cache.md)
for the unit-of-work helper and the cache-aside pattern — both are wired
in during this phase, not bolted on later.

## Swagger

See [references/swagger-openapi.md](references/swagger-openapi.md).

## Local development database

Transactions require a replica set — a plain standalone `mongod` will
reject them at runtime with a clear error, not silently skip the atomicity
guarantee. For local development, either:

- Run a single-node replica set locally (`mongod --replSet rs0`, then
  `rs.initiate()` once via `mongosh`), or
- Point local development at a free-tier MongoDB Atlas cluster, which is
  already a replica set.

Note whichever the developer picks in `docs/decisions.md`, since it's the
kind of environment detail a future contributor needs and won't find in
the code.
