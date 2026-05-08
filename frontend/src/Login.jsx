import React, { useState } from 'react';
import './style.css';

const Login = ({ onLogin }) => {
    const [isRightPanelActive, setIsRightPanelActive] = useState(false);

    const handleSignUpClick = () => setIsRightPanelActive(true);
    const handleSignInClick = () => setIsRightPanelActive(false);

    const submitLogin = (e) => {
        e.preventDefault();
        onLogin(); 
    };

    return (
        // Ce wrapper remplace l'ancien <body> pour tout centrer
        <div className="login-wrapper">
            <div className={`container ${isRightPanelActive ? 'right-panel-active' : ''}`} id="container">
                
                <div className="form-container sign-up-container">
                    <form action="#" onSubmit={(e) => e.preventDefault()}>
                        <h1>Create Account</h1>
                        <div className="social-container">
    {/* ======================================================================= */}
    {/* ZONE À MODIFIER : LIEN FACEBOOK */}
    {/* Remplacer "/facebook.html" par le vrai lien (ex: "https://facebook.com/alten") */}
    <a href="/facebook.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fab fa-facebook-f"></i>
    </a>

    {/* ZONE À MODIFIER : LIEN X (Ancien Twitter) */}
    {/* Remplacer "/x.html" par le vrai lien (ex: "https://x.com/alten") */}
    <a href="/x.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fab fa-twitter"></i>
    </a>

    {/* ZONE À MODIFIER : LIEN LINKEDIN */}
    {/* Remplacer "/linkedin.html" par le vrai lien (ex: "https://linkedin.com/company/alten") */}
    <a href="/linkedin.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fab fa-linkedin-in"></i>
    </a>
    {/* ======================================================================= */}
                        </div>
                        <span>or use your email for registration</span>
                        <input type="text" placeholder="Name" />
                        <input type="email" placeholder="Email" />
                        <input type="password" placeholder="Password" />
                        <button>Sign Up</button>
                    </form>
                </div>

                <div className="form-container sign-in-container">
                    <form action="#" onSubmit={submitLogin}>
                        <h1>Sign in</h1>
                        <div className="social-container">
    {/* ======================================================================= */}
    {/* ZONE À MODIFIER : LIEN FACEBOOK */}
    {/* Remplacer "/facebook.html" par le vrai lien (ex: "https://facebook.com/alten") */}
    <a href="/facebook.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fab fa-facebook-f"></i>
    </a>

    {/* ZONE À MODIFIER : LIEN X (Ancien Twitter) */}
    {/* Remplacer "/x.html" par le vrai lien (ex: "https://x.com/alten") */}
    <a href="/x.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fa-brands fa-x-twitter"></i>
    </a>

    {/* ZONE À MODIFIER : LIEN LINKEDIN */}
    {/* Remplacer "/linkedin.html" par le vrai lien (ex: "https://linkedin.com/company/alten") */}
    <a href="/linkedin.html" target="_blank" rel="noopener noreferrer" className="social">
        <i className="fab fa-linkedin-in"></i>
    </a>
    {/* ======================================================================= */}
                        </div>
                        <span>or use your account</span>
                        <input type="email" placeholder="Email" />
                        <input type="password" placeholder="Password" />
                        <a href="#">Forgot your password?</a>
                        <button type="submit">Sign In</button>
                    </form>
                </div>

                <div className="overlay-container">
                    <div className="overlay">
                        <div className="overlay-panel overlay-left">
                            <h1>Welcome Back!</h1>
                            <p>To keep connected with us please login with your personal info</p>
                            <button className="ghost" onClick={handleSignInClick}>Sign In</button>
                        </div>
                        <div className="overlay-panel overlay-right">
                            <h1>Hello, Friend!</h1>
                            <p>Enter your personal details and start journey with us</p>
                            <button className="ghost" onClick={handleSignUpClick}>Sign Up</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default Login;