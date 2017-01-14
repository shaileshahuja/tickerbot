# if query["result"]["action"] == 'register.email':
#     params = query["result"]["parameters"]
#     serializer = EmailSerializer(data={'email': params['email']})
#     try:
#         serializer.is_valid(raise_exception=True)
#         return self.send("Please enter your desired username",
#                          [self.prepare_context('register-email', {'email': params['email']})])
#     except ValidationError as e:
#         return self.send(e.detail.values()[0][0], [self.prepare_context('register-start')])
# if query["result"]["action"] == 'register.username':
#     params = query["result"]["parameters"]
#     context_params = APIAI.get_context_params(query, 'register-email')
#     serializer = RegisterUsernameSerializer(data={'username': params['username']})
#     try:
#         serializer.is_valid(raise_exception=True)
#         return self.send("Please enter your desired password",
#                          [self.prepare_context('register-username', {
#                              'username': params['username'],
#                              'email': context_params['email'],
#                          })])
#     except ValidationError as e:
#         return self.send(e.detail.values()[0][0],
#                          [self.prepare_context('register-email', {
#                              'email': context_params['email']
#                          })])
# if query["result"]["action"] == 'register.user':
#     params = query["result"]["parameters"]
#     context_params = APIAI.get_context_params(query, 'register-username')
#     serializer = RegisterSerializer(data={'username': context_params['username'],
#                                           'email': context_params['email'],
#                                           'password': params['password']})
#     try:
#         serializer.is_valid(raise_exception=True)
#         talk_user = serializer.save()
#         login(request, talk_user.user)
#         return self.send("Welcome, you have ${} cash left in your account".format(talk_user.cash),
#                          [self.prepare_context('user', {
#                              'session': request.session.session_key,
#                          }, lifespan=5)])
#     except ValidationError as e:
#         return self.send(e.detail.values()[0][0],
#                          [self.prepare_context('register-username',
#                                                {'username': context_params['username'],
#                                                 'email': context_params['email']})])
# if query["result"]["action"] == 'login.username':
#     params = query["result"]["parameters"]
#     serializer = LoginUsernameSerializer(data={'username': params['username']})
#     try:
#         serializer.is_valid(raise_exception=True)
#         return self.send("Please enter your password",
#                          [self.prepare_context('login-username', {
#                              'username': params['username']
#                          })])
#     except ValidationError as e:
#         return self.send(e.detail.values()[0][0], [self.prepare_context('login-start')])
# if query["result"]["action"] == 'login.user':
#     params = query["result"]["parameters"]
#     context_params = APIAI.get_context_params(query, 'login-username')
#     serializer = LoginSerializer(data={'username': context_params['username'],
#                                        'password': params['password']})
#     try:
#         serializer.is_valid(raise_exception=True)
#         user = authenticate(username=serializer.validated_data['username'],
#                             password=serializer.validated_data['password'])
#         if user is None:
#             raise AuthenticationFailed('Invalid username password combination')
#         login(request, user)
#         return self.send("Welcome, you have ${:.2f} left in your account".format(user.talkuser.cash),
#                          [self.prepare_context('user', {'session': request.session.session_key},
#                                                lifespan=5)])
#     except ValidationError as e:
#         return self.send(e.detail.values()[0][0],
#                          [self.prepare_context('login-username',
#                                                {'username': context_params['username']})])
#     except AuthenticationFailed as e:
#         return self.send(e.detail)