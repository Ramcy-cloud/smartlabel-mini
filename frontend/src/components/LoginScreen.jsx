import { useState } from 'react';
import { Button, Input, Typography } from 'antd';
import { LockOutlined, MailOutlined, TagsOutlined } from '@ant-design/icons';
import { login } from '../services/api';
import './LoginScreen.css';

const { Title, Text } = Typography;

const errorMessage = (error) => {
  const status = error?.response?.status;
  if (status === 401) return 'Email ou mot de passe incorrect.';
  if (status === 429) return 'Trop de tentatives, réessayez dans une minute.';
  if (status === 503) return "L'authentification n'est pas configurée sur le serveur (APP_EMAIL et APP_PASSWORD).";
  if (!error?.response) return 'Impossible de joindre le serveur. Vérifiez que le backend tourne.';
  return 'Connexion impossible.';
};

// Écran de connexion : même principe que celui du projet RAG PDF (email + mot de passe, jeton de session)
export default function LoginScreen({ onSuccess }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async (event) => {
    event.preventDefault();
    if (!email || !password) return;
    setLoading(true);
    setError('');
    try {
      await login(email, password);
      onSuccess();
    } catch (err) {
      setError(errorMessage(err));
      setPassword('');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-blob login-blob-green" />
      <div className="login-blob login-blob-blue" />

      <div className="login-card">
        <div className="login-header">
          <div className="login-logo"><TagsOutlined /></div>
          <Title level={2} style={{ margin: 0 }}>SmartLabel-Mini</Title>
          <Text type="secondary">Accédez à votre espace de tri de tickets</Text>
        </div>

        {error && <div className="login-error" role="alert">{error}</div>}

        <form onSubmit={submit} className="login-form">
          <Input
            size="large"
            type="email"
            autoComplete="username"
            prefix={<MailOutlined />}
            placeholder="Adresse email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            maxLength={254}
            required
          />
          <Input.Password
            size="large"
            autoComplete="current-password"
            prefix={<LockOutlined />}
            placeholder="Mot de passe"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            maxLength={256}
            required
          />
          <Button
            type="primary"
            htmlType="submit"
            size="large"
            block
            loading={loading}
            disabled={!email || !password}
            className="login-submit"
          >
            Se connecter
          </Button>
        </form>
      </div>
    </div>
  );
}
